import { execFileSync } from 'node:child_process'
import { readFile, writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const root = new URL('../../', import.meta.url)
const code = [
  'import json',
  'from attendflow.api.app import create_app',
  'print(json.dumps(create_app().openapi()))',
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
