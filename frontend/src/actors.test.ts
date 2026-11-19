import { afterEach, describe, expect, it, vi } from 'vitest'
import { reviewerFor } from './actors'

describe('reviewer identity', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
    window.history.replaceState({}, '', '/')
  })

  it('defaults to Ravi', () => {
    expect(reviewerFor('', true).id).toBe('E101')
    expect(reviewerFor('?as=E999', true).id).toBe('E101')
  })

  it('accepts ?as= in a dev build', () => {
    expect(reviewerFor('?as=E102', true)).toEqual({ id: 'E102', name: 'Sunita Rao' })
    expect(reviewerFor('?as=e201', true)).toEqual({ id: 'E201', name: 'Priya Sharma' })
  })

  it('ignores ?as= in a production build', () => {
    expect(reviewerFor('?as=E102', false).id).toBe('E101')
    expect(reviewerFor('?as=E201', false).id).toBe('E101')
  })

  it('reads the build flag when the module loads', async () => {
    window.history.replaceState({}, '', '/supervisor?as=E102')
    vi.stubEnv('DEV', false)
    vi.resetModules()
    expect((await import('./actors')).supervisorActor.id).toBe('E101')

    vi.stubEnv('DEV', true)
    vi.resetModules()
    expect((await import('./actors')).supervisorActor.id).toBe('E102')
  })
})
