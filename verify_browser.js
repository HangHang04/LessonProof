// Run through Playwright CLI against the local workbench; all model and system calls are real.
async page => {
  const checks=[], jobs=[], errors=[];
  const check=(condition,name)=>{if(!condition)throw new Error(name);checks.push(name);};
  page.on("pageerror",error=>errors.push(error.message));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto("http://127.0.0.1:8765/#home",{waitUntil:"domcontentloaded"});
  await page.reload({waitUntil:"domcontentloaded"}); // Refresh the session token after a service restart.
  await page.getByRole("heading",{name:"把问题留在课前。",exact:true}).waitFor();
  for(const title of ["缺失值与整数转换","数组数据读取与统计","读懂列表越界的错误信息"]) {
    await page.getByRole("article").filter({has:page.getByRole("heading",{name:title,exact:true})}).getByRole("button").click();
    await page.getByRole("checkbox",{name:"我已确认步骤、输入数据与教学预期报错。"}).waitFor();
    const id=page.url().split("#job/")[1];
    const read=()=>page.evaluate(async id=>{
      const token=document.querySelector('meta[name="lessonproof-token"]').content;
      return (await fetch("/api/jobs/"+id,{headers:{"X-LessonProof-Token":token}})).json();
    },id);
    const original=await read();
    await page.getByRole("checkbox").check();
    await page.getByRole("tab",{name:"运行证据",exact:true}).click();
    check(await page.getByRole("checkbox").isChecked(),title+"：切换标签保留确认");
    await page.getByRole("tab",{name:"运行证据",exact:true}).press("Home");
    check(await page.getByRole("tab",{name:"讲义与步骤",exact:true}).evaluate(el=>el===document.activeElement),"方向键切换标签和焦点");
    await page.getByRole("button",{name:"刷新",exact:true}).click();
    await page.getByRole("checkbox").waitFor();
    check(await page.getByRole("checkbox").isChecked(),title+"：刷新状态保留确认");
    // Hold the request briefly to reproduce navigating away while a mutation completes.
    if(!jobs.length) {
      let release;
      const gate=new Promise(resolve=>release=resolve);
      await page.route("**/api/jobs/"+id+"/run",async route=>{await gate;await route.continue();});
      const completed=page.waitForResponse(response=>response.url().endsWith("/"+id+"/run"));
      await page.getByRole("button",{name:"确认并开始试跑",exact:true}).click();
      await page.getByRole("navigation",{name:"主导航"}).getByRole("link",{name:"工作台",exact:true}).click();
      await page.getByRole("heading",{name:"把问题留在课前。",exact:true}).waitFor();
      release();await completed;
      // Readback follows the completed mutation; let that response arrive before checking the view.
      await page.locator('#view[aria-busy="true"]').waitFor({state:"hidden"});
      check(await page.getByRole("heading",{name:"把问题留在课前。",exact:true}).isVisible(),"请求完成后保留用户当前页面");
      await page.unroute("**/api/jobs/"+id+"/run");
      await page.goto("http://127.0.0.1:8765/#job/"+id,{waitUntil:"domcontentloaded"});
    }else await page.getByRole("button",{name:"确认并开始试跑",exact:true}).click();
    if(title==="缺失值与整数转换") {
      await page.getByRole("button",{name:"采用修订并复测",exact:true}).waitFor({timeout:300000});
      await page.getByText("教师复核：认为这是 AI 误报？",{exact:true}).click();
      const reason="开发体验检查：暂存的复核意见，尚未提交或批准。";
      await page.getByRole("textbox",{name:"说明为什么无需修改（至少 10 字）"}).fill(reason);
      await page.getByRole("checkbox",{name:"我已阅读修改对照，同意采用这些修订。"}).check();
      await page.getByRole("tab",{name:"运行证据",exact:true}).click();
      await page.getByRole("tab",{name:"问题与修订",exact:true}).click();
      check(await page.getByRole("textbox").inputValue()===reason,"保留复核意见与展开状态");
      check(await page.getByRole("checkbox").isChecked(),"保留修订确认");
      await page.screenshot({path:"output/playwright/ux-review-after.png",fullPage:true});
      await page.getByRole("button",{name:"采用修订并复测",exact:true}).click();
    }
    await page.getByRole("button",{name:"审核通过",exact:true}).waitFor({timeout:300000});
    check(!await page.getByRole("checkbox").isChecked(),"运行完成后需要重新确认审核");
    await page.getByRole("tab",{name:"运行证据",exact:true}).click();
    const reviewed=await read();
    check(reviewed.runs.at(-1).assessment.status==="passed",title+"：实际执行通过");
    check(reviewed.runs.at(-1).ai_status==="completed"&&reviewed.runs.at(-1).ai.findings.length===0,title+"：实际 AI 审阅完成");
    check(reviewed.contract_sha256===original.contract_sha256,"复测使用原验收标准");
    if(title==="缺失值与整数转换")check(reviewed.revision===1,"历史讲义已保存修订版");
    if(title==="读懂列表越界的错误信息")check(reviewed.revision===0&&reviewed.runs.at(-1).execution.steps.some(s=>s.error_type==="IndexError"),"教学报错保留并继续执行");
    await page.getByRole("checkbox").check();
    await page.getByRole("button",{name:"审核通过",exact:true}).click();
    await page.getByRole("button",{name:"生成交付包",exact:true}).waitFor();
    await page.getByRole("button",{name:"生成交付包",exact:true}).click();
    await page.getByRole("heading",{name:"课程已交付，回读一致。",exact:true}).waitFor({timeout:60000});
    const download=page.waitForEvent("download");
    await page.getByRole("button",{name:"下载课程包",exact:true}).first().click();
    await (await download).saveAs("output/playwright/"+id+"-course.zip");
    const evidence=page.waitForEvent("download");
    await page.getByRole("button",{name:"下载完整证据",exact:true}).click();
    await (await evidence).saveAs("output/playwright/"+id+"-evidence.zip");
    const delivered=await read();check(delivered.delivery.readback_matched,title+"：交付回读一致");
    jobs.push({id,title,revision:delivered.revision,version_hash:delivered.version_hash,contract_sha256:delivered.contract_sha256});
    await page.goto("http://127.0.0.1:8765/student/"+id,{waitUntil:"domcontentloaded"});
    await page.getByRole("heading",{name:title,exact:true}).first().waitFor();
    check(await page.locator(".lecture h2").count()>0,"学生讲义正常排版");
    await page.setViewportSize({width:390,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),"学生页手机宽度正常");
    await page.goto("http://127.0.0.1:8765/#job/"+id,{waitUntil:"domcontentloaded"});
    await page.getByRole("heading",{name:title,exact:true}).waitFor();
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),"工作台手机宽度正常");
    check(await page.locator(".next-step").evaluate(el=>el.getBoundingClientRect().top<document.querySelector(".panel").getBoundingClientRect().top),"手机先显示下一步操作");
    await page.emulateMedia({reducedMotion:"reduce"});
    check(await page.locator(".btn").first().evaluate(el=>getComputedStyle(el).transitionDuration==="0s"),"减少动效偏好生效");
    await page.emulateMedia({reducedMotion:"no-preference"});
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole("navigation",{name:"主导航"}).getByRole("link",{name:"工作台",exact:true}).click();
    await page.getByRole("heading",{name:"把问题留在课前。",exact:true}).waitFor();
  }
  await page.getByRole("button",{name:"+ 导入课程",exact:true}).click();
  check(await page.getByRole("dialog").isVisible(),"导入前说明课程格式");
  await page.screenshot({path:"output/playwright/ux-import-after.png"});
  await page.keyboard.press("Escape");check(!await page.getByRole("dialog").isVisible(),"Escape 关闭导入说明");
  check(errors.length===0,"浏览器未出现脚本错误");
  await page.screenshot({path:"output/playwright/ux-home-after.png",fullPage:true});
  return {checks,jobs,errors};
}
