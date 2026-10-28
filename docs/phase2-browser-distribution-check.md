# 阶段二数字题分布浏览器验收记录（旧授权口径）

本记录保留B01执行当时的界面与结果。后来按用户确认改为**自动纳入所有有效同版问卷**，当前页面调用`all-survey-statistics`，不再以问卷所有者授权决定范围。因此下文“未授权只含A卷、授权后含B卷、撤销后排除B卷”只证明保留的旧接口与旧界面曾按当时设计工作，**不能作为当前统计口径的验收结论**。当前页面复测见[第二阶段测试用例P2-19和P2-21](phase2-test-cases.md)及B02截图。

## 测试方法与环境

B01在独立Microsoft Edge无用户资料会话中完成。Playwright驱动真实页面的登录、创建、分享、选题、发布、填写、授权、撤销和统计刷新，并在关键状态截取整页截图。这是浏览器界面操作测试，不是人工逐项点击的手验。测试使用合成账号和隔离库127.0.0.1:29141/unit6_browser，页面为http://127.0.0.1:15173/，没有连接正式业务库。

完整机器记录及截图SHA-256见[verification-result.json](evidence/phase2/phase2-browser-distribution-20261027063337/verification-result.json)。截图均未包含密码或令牌。

## B01 步骤与实际结果

1. 作者A创建选答数字题“B01年龄分布-20261027063337”，限制整数0—120，生成版本1，并按用户名分享给B。A、B各创建并发布一份问卷，分别选入同一版本，产生不同的问卷题目实例。B初始未授权统计。[版本截图](evidence/phase2/phase2-browser-distribution-20261027063337/01-author-version1.png)、[A问卷截图](evidence/phase2/phase2-browser-distribution-20261027063337/02-A-published.png)、[B问卷截图](evidence/phase2/phase2-browser-distribution-20261027063337/03-B-published-unconsented.png)。
2. 五名不同合成填写者分别通过页面向A问卷提交22，向B问卷提交42，均为每人每卷一份。B未授权时，A的版本统计只纳入A问卷：参与问卷1、答卷／到达／回答各5、平均22，非零分布“等于22”计5。[未授权截图](evidence/phase2/phase2-browser-distribution-20261027063337/04-A-only-five-answers.png)。
3. B在问卷编辑页点击“明确授权纳入”。A刷新后显示参与问卷2、答卷／到达／回答各10、平均32；非零区间20≤数值<25和40≤数值≤45各5。[授权截图](evidence/phase2/phase2-browser-distribution-20261027063337/05-B-granted.png)、[汇总截图](evidence/phase2/phase2-browser-distribution-20261027063337/06-two-surveys-ten-answers.png)。
4. 第六名不同填写者通过页面仅向B问卷提交70。A刷新后显示“样本不足”，答卷层面的数量、均值与分布不再显示具体值，也没有保留上一步的旧统计。[抑制截图](evidence/phase2/phase2-browser-distribution-20261027063337/07-sparse-bin-suppressed.png)。
5. B撤销授权，A再次刷新。结果恢复为参与问卷1、答卷／到达／回答各5、平均22、“等于22”计5。隔离库只读核对确认B问卷及其6份答卷仍存在，撤销没有删改历史数据。[撤销截图](evidence/phase2/phase2-browser-distribution-20261027063337/08-B-revoked.png)、[撤销后统计截图](evidence/phase2/phase2-browser-distribution-20261027063337/09-revoked-A-only.png)。

**结果：通过。** 页面实际结果与自动API测试的授权、分布和稀疏区间抑制预期一致。隔离库只读复核了两份已发布问卷、各自的来源实例、A问卷5份22、B问卷5份42加1份70、分享关系及最终撤销状态。测试未覆盖不同浏览器或多人同时操作；不将本项写成人工手验。

