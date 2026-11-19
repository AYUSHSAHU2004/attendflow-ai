import { afterEach, describe, expect, it, vi } from 'vitest'
import { reviewerFor, workerFor } from './actors'

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

  it('acts as Priya on the admin page; ?as= only in a dev build', async () => {
    window.history.replaceState({}, '', '/admin?as=E101')
    vi.stubEnv('DEV', false)
    vi.resetModules()
    expect((await import('./actors')).adminActor.id).toBe('E201')

    vi.stubEnv('DEV', true)
    vi.resetModules()
    expect((await import('./actors')).adminActor.id).toBe('E101')

    window.history.replaceState({}, '', '/admin')
    vi.resetModules()
    expect((await import('./actors')).adminActor).toEqual({ id: 'E201', name: 'Priya Sharma' })
  })

  it('acts as Amit in the inbox; ?as=E004 (Neha) only in a dev build', async () => {
    expect(workerFor('', true).id).toBe('E001')
    expect(workerFor('?as=e004', true)).toEqual({ id: 'E004', name: 'Neha Gupta' })
    expect(workerFor('?as=E101', true).id).toBe('E001') // reviewers are not workers
    expect(workerFor('?as=E004', false).id).toBe('E001')

    window.history.replaceState({}, '', '/?as=E004')
    vi.stubEnv('DEV', false)
    vi.resetModules()
    expect((await import('./actors')).workerActor.id).toBe('E001')

    vi.stubEnv('DEV', true)
    vi.resetModules()
    expect((await import('./actors')).workerActor.id).toBe('E004')
  })
})
