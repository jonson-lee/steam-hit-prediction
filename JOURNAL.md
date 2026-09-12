# 更新日记

按日期追加，最新在上。格式：`日期 - 谁 - 做了什么 / 结论 / 下一步`。

---

## 2026-09-12 - Project Team

- 完成六张 Steam CSV 的正式数据验收：ZIP/CRC、SHA-256、结构、主键、重复、缺失、日期、owners 区间、跨表覆盖均已检查
- 结论：文件质量 Pass，分析可用性 Conditional Go
- 发现原 owners 年内前 10% 方案受 13 个粗区间和大量并列影响：整体正类 20.97%，2019 年为 100%，不再作为主标签
- 锁定主标签：同发行年份总评价数前 10%，并排除不完整的 2019
- 锁定时间切分：≤2016 训练、2017 验证、2018 测试
- SteamSpy tags/tag votes 判定为发行后泄漏；价格、成就及辅助表字段仅作快照敏感性分析
- 时间安全 developer/publisher 规则在 2018 年得到 ROC-AUC 0.698、Average Precision 0.321、预期 Lift@10% 4.08，证明数据有可建模信号
- 新增 `scripts/validate_steam_data.py`、`data/README.md` 和 `docs/` 项目文档
- 完成公开发布审查：未发现凭据、本机路径或 Notebook 输出；原始数据与旧 ZIP 保持忽略
- 云端更新缩减为 README、proposal、EDA、现有 JOURNAL、依赖、验证脚本、数据说明和必要验收报告；内部上下文、决策、下一步及机器审计 JSON 仅保留本地

**下一步**

- [ ] 按已锁定标签与时间切分重构 EDA notebook
- [ ] 建立规则、Logistic Regression 和一个树集成模型的统一流水线

## 2026-09-09 - Waylen
- 定题：Steam 游戏爆款预测（发行商预算分配决策）
- 团队 7 人组队完成
- 数据下载完毕：steam.csv（27,075 × 18）等 6 个文件
- 写好提案初稿 `Project_Proposal_Steam_Game_Success.md`（标签方案 A/B、A-B 字段切分、泄漏红线）
- 建好 `EDA_Steam.ipynb`，待跑：字段核对 / owners 区间转中点 / 缺失值 / 年份分布 / 两个标签方案不平衡度

**下一步**
- [x] 2026-09-12 已完成数据验收；A/B 旧方案由总评价量年内前 10% 主标签取代
- [x] 2026-09-12 已完成数据 README 和字段/时间戳边界说明
