import { describe, expect, it } from 'vitest'
import type { TaskSettings } from '../src/services/api'

describe('task settings contract', () => {
  it('does not define a separate frontend default object', () => {
    const settings: Partial<TaskSettings> = {}
    expect(Object.keys(settings)).toHaveLength(0)
  })
})

