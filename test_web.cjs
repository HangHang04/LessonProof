// Small, dependency-free check of the renderer used by both reading views.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({document:{querySelector:()=>null}});
vm.runInContext(fs.readFileSync('web/lesson.js','utf8'), context);
const render = context.renderLesson;
assert.match(render('# 标题\n## 步骤 a\n正文 `code`'), /<h1>标题<\/h1><h2>步骤 a<\/h2><p>正文 <code>code<\/code><\/p>/);
assert.match(render('[来源](https://example.com/source)'), /href="https:\/\/example.com\/source"/);
for(const input of ['<img src=x onerror=alert(1)>','[点击](javascript:alert(1))','[来源](https://x.test/"onmouseover="alert(1))']) {
  const html=render(input);
  assert.ok(!html.includes('<img') && !html.includes('href="javascript:') && !html.includes('"onmouseover="'));
}
assert.match(render('```python\n<x>\n```'), /<pre>&lt;x&gt;\n<\/pre>/);
console.log('Shared lesson renderer: headings, code, source links and HTML escaping passed.');
