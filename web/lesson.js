"use strict";
function escapeLessonHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function renderLesson(text) {
  let fenced = false;
  return text.split("\n").map(line => {
    if (line.startsWith("```")) {fenced=!fenced;return fenced?"<pre>":"</pre>";}
    if (fenced) return escapeLessonHTML(line)+"\n";
    const safe=escapeLessonHTML(line).replace(/`([^`]+)`/g,"<code>$1</code>")
      .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    if (line.startsWith("## ")) return `<h2>${safe.slice(3)}</h2>`;
    if (line.startsWith("# ")) return `<h1>${safe.slice(2)}</h1>`;
    return line.trim() ? `<p>${safe}</p>` : "";
  }).join("") + (fenced ? "</pre>" : "");
}
const studentLesson=document.querySelector("#student-lesson");
if(studentLesson)studentLesson.innerHTML=renderLesson(studentLesson.textContent);
