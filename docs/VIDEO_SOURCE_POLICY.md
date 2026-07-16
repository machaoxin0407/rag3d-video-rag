# 视频数据来源与许可审计规范

## 1. 目标

本规范用于建立可部署产品和可复现实验共用的视频数据入口。它是项目内部的风险控制流程，不替代专业法律意见。

## 2. 可接受来源

按优先级使用：

1. 团队自录并取得拍摄、科研和发布授权；
2. CC0、CC BY、CC BY-SA 视频；
3. 厂商或创作者明确书面授权的视频。

CC BY-NC、CC BY-NC-SA 和 CC BY-NC-ND 不进入面向部署的训练集。带 ND 条款的视频不切片、不转码、不生成衍生发布物。许可未知或普通平台标准许可的视频只登记为候选，不下载。

## 3. 两级审核

任何第三方视频必须经过两个人独立审核：

1. 初审人记录作者、来源页、许可、许可链接、允许的行为和风险；
2. 复审人重新打开来源页，确认许可没有抄错，并检查隐私、人物、商标、背景音乐和衍生素材；
3. 只有 `final_decision=accept` 的记录才允许进入下载队列；
4. `scope_review`、`hold_privacy` 和 `reject_scope` 均不得下载。

即使平台已有许可证审查，也不能省略本项目的人工复审。

## 4. 下载与留存

- 原始视频存放于 `data_video/raw/`，不得提交 Git；
- 下载后计算 SHA-256，回填 inventory；
- 保存来源页面、许可页面、获取日期和署名文字；
- 默认论文只发布 URL、video ID、时间段和标注；
- CC BY-SA 衍生视频必须保持兼容的 ShareAlike 条款；
- 自录视频的授权文件单独加密保存，不提交公开仓库；
- 删除文件中的地理位置和设备序列号等无关元数据。

## 5. 数据集划分

- 同一原始视频的片段不得跨 train/dev/test；
- 同一作者或同一拍摄场景尽量只进入一个 split；
- 公开许可视频主要用于 train/dev；
- 自录视频优先作为独立 test；
- 测试集冻结后，不得根据测试答案修改规则、提示词或阈值。

## 6. 验收标准

每个产品类别进入第一阶段必须同时满足：

- 至少15条最终许可通过的视频；
- 覆盖至少3个操作、维护或故障 procedure；
- 至少有2条可自录的独立测试视频；
- 所有接受条目完成双人审核；
- 所有下载文件具有 SHA-256 和署名记录。

## 7. 规则依据

- [YouTube 官方许可证类型说明](https://support.google.com/youtube/answer/2797468?hl=en)
- [Creative Commons 六类许可证说明](https://creativecommons.org/share-your-work/use-remix/cc-licenses/)
- [Wikimedia Commons 站外复用说明](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/en)

来源平台的许可标记只能作为证据的一部分，仍需核查上传者是否可能使用了背景音乐、品牌素材或其他第三方内容。
