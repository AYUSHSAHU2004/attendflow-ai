"""Provision demo accounts, reset employee passwords, and clear login throttles."""

import argparse
import json
from getpass import GetPassWarning, getpass
from ipaddress import ip_address
from warnings import catch_warnings, simplefilter

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from attendflow.api.auth import unlock_login
from attendflow.cases import service
from attendflow.clock import DemoClock
from attendflow.config import get_settings
from attendflow.db.credentials import hash_password, normalize_email, valid_email
from attendflow.db.models import AuthSessionRow, EmployeeRow
from attendflow.db.seed import seed_demo_once
from attendflow.db.session import make_engine, make_session_factory
from attendflow.policy.models import load_policy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-demo", help="Bootstrap or provision the synthetic demo accounts")
    password = commands.add_parser(
        "set-password", help="Set an employee password and revoke sessions"
    )
    password.add_argument("employee_id")
    password.add_argument("--email", help="Required when an employee has no email")
    unlock = commands.add_parser("unlock", help="Clear a lockout in the running application")
    target = unlock.add_mutually_exclusive_group(required=True)
    target.add_argument("--email")
    target.add_argument("--ip")
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "unlock":
        if settings.auth_mode != "session":
            parser.error("Unlock requires session authentication")
        if args.email is not None:
            unlock_login(settings.session_secret, "email", normalize_email(args.email))
        else:
            try:
                address = str(ip_address(args.ip))
            except ValueError:
                parser.error("Provide a valid IPv4 or IPv6 address")
            unlock_login(settings.session_secret, "ip", address)
        print("Lockout cleared for the next login attempt.")
        return

    engine = make_engine(settings.database_url)
    sessions = make_session_factory(engine)
    try:
        if args.command == "seed-demo":
            if not settings.demo_password:
                parser.error("Set ATTENDFLOW_DEMO_PASSWORD before seeding")
            with sessions() as session:
                with session.begin():
                    counts = seed_demo_once(
                        session,
                        settings.data_dir,
                        extra_week=settings.demo_extra_week,
                        demo_password=settings.demo_password,
                    )
                detection = service.run_detection(
                    session,
                    load_policy(settings.data_dir / "policy.json"),
                    DemoClock(settings.as_of),
                    auto_resolve=settings.auto_resolve_enabled,
                )
            print(json.dumps({**counts, "exceptions_found": detection.found}))
            return

        with catch_warnings():
            simplefilter("error", GetPassWarning)
            try:
                value = getpass("New password: ")
                if not 12 <= len(value) <= 1024:
                    parser.error("Use a password between 12 and 1024 characters")
                if value != getpass("Confirm password: "):
                    parser.error("Passwords do not match")
            except (GetPassWarning, EOFError):
                parser.error("Run password setup from an interactive terminal")
        with sessions.begin() as session:
            employee = session.scalar(
                select(EmployeeRow)
                .where(EmployeeRow.employee_id == args.employee_id.upper())
                .with_for_update()
            )
            if employee is None:
                parser.error("Employee does not exist")
            email = normalize_email(args.email) if args.email is not None else employee.email
            if not email or not valid_email(email):
                parser.error("Provide a valid --email for this employee")
            employee.email = email
            employee.password_hash = hash_password(value)
            session.execute(
                delete(AuthSessionRow).where(
                    AuthSessionRow.employee_id == employee.employee_id,
                )
            )
        print("Credentials updated and existing sessions revoked.")
    except IntegrityError:
        parser.error("Credentials could not be saved. Check for an email already in use.")
    except ValueError as error:
        parser.error(str(error))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
