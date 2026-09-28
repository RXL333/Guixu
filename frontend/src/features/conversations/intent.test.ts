import { describe, expect, it } from 'vitest'
import { isNamingRequest } from './intent'

describe('naming intent', () => {
  it('routes explicit naming commands', () => {
    expect(isNamingRequest('帮我把所有文件文件进行命名')).toBe(true)
    expect(isNamingRequest('请给这些照片重命名')).toBe(true)
    expect(isNamingRequest('生成命名方案')).toBe(true)
  })
  it('keeps questions and classification in chat', () => {
    expect(isNamingRequest('文件怎么命名比较合适？')).toBe(false)
    expect(isNamingRequest('把照片按照场景分类')).toBe(false)
  })
})
