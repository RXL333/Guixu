/** Route explicit file actions; questions and rule discussions stay in chat. */
export function isNamingRequest(message: string): boolean {
  const value = message.trim()
  if (/[？?]$/.test(value) || /^(请)?(如何|怎么|能否|可以|讨论|解释|说明|建议|告诉|为什么)/.test(value)) return false
  return /(命名|重命名|起名|改名)/.test(value)
    && /(文件|照片|图片|目录|文件夹|命名方案)/.test(value)
    && /^(请|帮我|给|为|把|将|开始|进行|生成|重新|现在)/.test(value)
}
