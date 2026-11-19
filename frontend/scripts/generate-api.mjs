import { execFileSync } from 'node:child_process'
import { readFile, writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const root = new URL('../../', import.meta.url)
// Always generated with demo mode on, so the typed client also knows the DEMO_MODE-only
// routes (the server serves them only when ATTENDFLOW_DEMO_MODE=true). Independent of .env.
const code = [
  'import json',
  'from dataclasses import replace',
  'from attendflow.api.app import create_app',
  'from attendflow.config import get_settings',
  'print(json.dumps(create_app(replace(get_settings(env_file=None), demo_mode=True)).openapi()))',
].join('; ')
const python = process.env.ATTENDFLOW_PYTHON
const output = execFileSync(python || 'uv', python ? ['-c', code] : ['run', 'python', '-c', code], {
  cwd: root,
  encoding: 'utf8',
  env: { ...process.env, LOG_LEVEL: 'WARNING' },
})
const generated = '// Generated from FastAPI OpenAPI. Run npm run api:generate.\n' +
  astToString(await openapiTS(JSON.parse(output)))
const target = new URL('../src/api.generated.ts', import.meta.url)
if (process.argv.includes('--check')) {
  if (generated !== await readFile(target, 'utf8')) {
    throw new Error('OpenAPI types are out of date. Run npm run api:generate.')
  }
} else {
  await writeFile(target, generated)
}
