# 第二阶段浏览器验收截图

截图按实际执行方式标注。本人口述反馈和手工截图与AI驱动页面操作分别记录；M16的409为页面模拟响应。未标原始时分秒的截图只标批次，不以文件复制时间代替拍摄时间。数字与文本完整流程中的新增答卷通过正常填写页提交。

## 截图索引

| 编号 | 原截图时间或批次 | 内容 | 对应用例 | 执行方式 |
| --- | --- | --- | --- | --- |
| [S01](images/phase2-manual/01-bank-renamed.png) | 2026-10-27 21:13:59 | 题库改名成功 | P2-17 | 本人手工操作 |
| [S02](images/phase2-manual/02-version-created.png) | 2026-10-27 21:20:11 | 版本2创建，保留版本1和来源关系 | P2-07 | 本人手工操作 |
| [S03](images/phase2-manual/03-bank-fixed-v1.png) | 2026-10-27 21:21:32 | 题库固定版本1，未自动跟随当前版本 | P2-08 | 本人手工操作 |
| [S04](images/phase2-manual/04-bank-switched-v2.png) | 2026-10-27 21:21:57 | 显式切换后固定版本2 | P2-08 | 本人手工操作 |
| [S05](images/phase2-manual/05-version-history.png) | 2026-10-27（原图未标时分秒） | 版本3、4保留旧内容并记录来源版本1 | P2-07 | 本人手工操作 |
| [S06](images/phase2-manual/06-version5-from-v2.png) | 2026-10-27（原图未标时分秒） | 基于版本2创建版本5 | P2-07、P2-10 | 本人手工操作 |
| [S07](images/phase2-manual/07-published-keeps-v1.png) | 2026-10-27（原图未标时分秒） | 新增版本后已发布问卷保持版本1 | P2-10 | 本人手工操作 |
| [S08](images/phase2-manual/08-draft-keeps-v2.png) | 2026-10-27（原图未标时分秒） | 新增版本后草稿保持版本2 | P2-10 | 本人手工操作 |
| [S09](images/phase2-manual/09-usage-tracking.png) | 2026-10-27（原图未标时分秒） | 查询版本1与版本2的问卷使用关系 | P2-09 | 本人手工操作 |
| [S10](images/phase2-manual/10-share-revoked.png) | 2026-10-27（原图未标时分秒） | 撤销后显示暂无有效分享，使用记录仍在 | P2-09 | 本人手工操作 |
| [S11](images/phase2-manual/11-picker-after-revoke.png) | 2026-10-27（原图未标时分秒） | B的新草稿不再显示被撤销的年龄题 | P2-09 | 本人手工操作 |
| [S12](images/phase2-manual/12-age-a-published.png) | 2026-10-27（原图未标时分秒） | 本人配置并发布手验年龄A | P2-13 | 本人手工操作 |
| [S13](images/phase2-manual/13-age-b-published.png) | 2026-10-27 22:59:59 | 本人配置并发布手验年龄B | P2-13 | 本人手工操作 |
| [S14](evidence/phase2/phase2-gap-browser-20261027072710/01-all-surveys-no-consent.png) | 2026-10-27（B02批次） | 无需旧授权仍显示两卷汇总，稀疏样本抑制 | P2-19、P2-21 | AI辅助浏览器操作 |
| [S15](evidence/phase2/phase2-gap-browser-20261027072710/02-bank-renamed.png) | 2026-10-27（B02批次） | 题库改名 | P2-17、P2-21 | AI辅助浏览器操作 |
| [S16](evidence/phase2/phase2-gap-browser-20261027072710/03-bank-removed.png) | 2026-10-27（B02批次） | 题库归档后不再列出 | P2-17、P2-21 | AI辅助浏览器操作 |
| [S17](evidence/phase2/phase2-gap-browser-20261027072710/04-old-question-saved.png) | 2026-10-27（B02批次） | 旧问卷题目显式保存 | P2-18、P2-21 | AI辅助浏览器操作 |
| [S18](evidence/phase2/phase2-gap-browser-20261027072710/05-imported-version.png) | 2026-10-27（B02批次） | 显式保存产生首版本 | P2-18、P2-21 | AI辅助浏览器操作 |
| [S19](evidence/phase2/manual-age-browser-20261027-230604/statistics.png) | 2026-10-27（完整流程批次） | 两卷十份答卷，均值32及区间分布 | P2-13、P2-19 | AI辅助浏览器操作 |
| [S20](evidence/phase2/phase2-complete-browser-20261027-01/numeric-r6-filled-70.png) | 2026-10-27（完整流程批次） | R6从填写页输入70 | P2-13 | AI辅助浏览器操作 |
| [S21](evidence/phase2/phase2-complete-browser-20261027-01/numeric-r6-submitted.png) | 2026-10-27（完整流程批次） | R6正常页面提交成功 | P2-13 | AI辅助浏览器操作 |
| [S22](evidence/phase2/phase2-complete-browser-20261027-01/numeric-suppressed.png) | 2026-10-27（完整流程批次） | 稀疏数字区间触发样本抑制 | P2-13 | AI辅助浏览器操作 |
| [S23](evidence/phase2/phase2-complete-browser-20261027-01/text-overview-statistics.png) | 2026-10-27（完整流程批次） | 同内容版本合并、不同版本分组及重复文本频次 | P2-20 | AI辅助浏览器操作 |
| [S24](evidence/phase2/phase2-complete-browser-20261027-01/text-v2-statistics.png) | 2026-10-27（完整流程批次） | 版本2单独统计，单次文本不显示 | P2-20 | AI辅助浏览器操作 |
| [S25](evidence/phase2/unit6-browser-20261025/version1-statistics.png) | 2026-10-25（早期验收批次） | 早期授权接口的同版汇总，保留作历史证据 | M13、P2-06 | AI辅助浏览器操作；早期授权口径 |

## 图集

<a id="s01"></a>

### S01 题库改名成功

2026-10-27 21:13:59；本人手工操作；对应P2-17。

![S01 题库改名成功](images/phase2-manual/01-bank-renamed.png)

<a id="s02"></a>

### S02 版本2创建，保留版本1和来源关系

2026-10-27 21:20:11；本人手工操作；对应P2-07。

![S02 版本2创建，保留版本1和来源关系](images/phase2-manual/02-version-created.png)

<a id="s03"></a>

### S03 题库固定版本1，未自动跟随当前版本

2026-10-27 21:21:32；本人手工操作；对应P2-08。

![S03 题库固定版本1，未自动跟随当前版本](images/phase2-manual/03-bank-fixed-v1.png)

<a id="s04"></a>

### S04 显式切换后固定版本2

2026-10-27 21:21:57；本人手工操作；对应P2-08。

![S04 显式切换后固定版本2](images/phase2-manual/04-bank-switched-v2.png)

<a id="s05"></a>

### S05 版本3、4保留旧内容并记录来源版本1

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-07。

![S05 版本3、4保留旧内容并记录来源版本1](images/phase2-manual/05-version-history.png)

<a id="s06"></a>

### S06 基于版本2创建版本5

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-07、P2-10。

![S06 基于版本2创建版本5](images/phase2-manual/06-version5-from-v2.png)

<a id="s07"></a>

### S07 新增版本后已发布问卷保持版本1

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-10。

![S07 新增版本后已发布问卷保持版本1](images/phase2-manual/07-published-keeps-v1.png)

<a id="s08"></a>

### S08 新增版本后草稿保持版本2

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-10。

![S08 新增版本后草稿保持版本2](images/phase2-manual/08-draft-keeps-v2.png)

<a id="s09"></a>

### S09 查询版本1与版本2的问卷使用关系

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-09。

![S09 查询版本1与版本2的问卷使用关系](images/phase2-manual/09-usage-tracking.png)

<a id="s10"></a>

### S10 撤销后显示暂无有效分享，使用记录仍在

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-09。

![S10 撤销后显示暂无有效分享，使用记录仍在](images/phase2-manual/10-share-revoked.png)

<a id="s11"></a>

### S11 B的新草稿不再显示被撤销的年龄题

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-09。

![S11 B的新草稿不再显示被撤销的年龄题](images/phase2-manual/11-picker-after-revoke.png)

<a id="s12"></a>

### S12 本人配置并发布手验年龄A

2026-10-27（原图未标时分秒）；本人手工操作；对应P2-13。

![S12 本人配置并发布手验年龄A](images/phase2-manual/12-age-a-published.png)

<a id="s13"></a>

### S13 本人配置并发布手验年龄B

2026-10-27 22:59:59；本人手工操作；对应P2-13。

![S13 本人配置并发布手验年龄B](images/phase2-manual/13-age-b-published.png)

<a id="s14"></a>

### S14 无需旧授权仍显示两卷汇总，稀疏样本抑制

2026-10-27（B02批次）；AI辅助浏览器操作；对应P2-19、P2-21。

![S14 无需旧授权仍显示两卷汇总，稀疏样本抑制](evidence/phase2/phase2-gap-browser-20261027072710/01-all-surveys-no-consent.png)

<a id="s15"></a>

### S15 题库改名

2026-10-27（B02批次）；AI辅助浏览器操作；对应P2-17、P2-21。

![S15 题库改名](evidence/phase2/phase2-gap-browser-20261027072710/02-bank-renamed.png)

<a id="s16"></a>

### S16 题库归档后不再列出

2026-10-27（B02批次）；AI辅助浏览器操作；对应P2-17、P2-21。

![S16 题库归档后不再列出](evidence/phase2/phase2-gap-browser-20261027072710/03-bank-removed.png)

<a id="s17"></a>

### S17 旧问卷题目显式保存

2026-10-27（B02批次）；AI辅助浏览器操作；对应P2-18、P2-21。

![S17 旧问卷题目显式保存](evidence/phase2/phase2-gap-browser-20261027072710/04-old-question-saved.png)

<a id="s18"></a>

### S18 显式保存产生首版本

2026-10-27（B02批次）；AI辅助浏览器操作；对应P2-18、P2-21。

![S18 显式保存产生首版本](evidence/phase2/phase2-gap-browser-20261027072710/05-imported-version.png)

<a id="s19"></a>

### S19 两卷十份答卷，均值32及区间分布

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-13、P2-19。

![S19 两卷十份答卷，均值32及区间分布](evidence/phase2/manual-age-browser-20261027-230604/statistics.png)

<a id="s20"></a>

### S20 R6从填写页输入70

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-13。

![S20 R6从填写页输入70](evidence/phase2/phase2-complete-browser-20261027-01/numeric-r6-filled-70.png)

<a id="s21"></a>

### S21 R6正常页面提交成功

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-13。

![S21 R6正常页面提交成功](evidence/phase2/phase2-complete-browser-20261027-01/numeric-r6-submitted.png)

<a id="s22"></a>

### S22 稀疏数字区间触发样本抑制

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-13。

![S22 稀疏数字区间触发样本抑制](evidence/phase2/phase2-complete-browser-20261027-01/numeric-suppressed.png)

<a id="s23"></a>

### S23 同内容版本合并、不同版本分组及重复文本频次

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-20。

![S23 同内容版本合并、不同版本分组及重复文本频次](evidence/phase2/phase2-complete-browser-20261027-01/text-overview-statistics.png)

<a id="s24"></a>

### S24 版本2单独统计，单次文本不显示

2026-10-27（完整流程批次）；AI辅助浏览器操作；对应P2-20。

![S24 版本2单独统计，单次文本不显示](evidence/phase2/phase2-complete-browser-20261027-01/text-v2-statistics.png)

<a id="s25"></a>

### S25 早期授权接口的同版汇总，保留作历史证据

2026-10-25（早期验收批次）；AI辅助浏览器操作；早期授权口径；对应M13、P2-06。

![S25 早期授权接口的同版汇总，保留作历史证据](evidence/phase2/unit6-browser-20261025/version1-statistics.png)
