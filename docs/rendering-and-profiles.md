# JC v3 展示与个人 profile 边界

## 结论

[有理有据的][高等] `jc evaluate`只生成机器结果、审计事件和`graph.json`，不会默认生成Markdown、Mermaid或HTML。展示必须显式执行：

```powershell
jc render <run_id> --format markdown --audience agent --json
jc render <run_id> --format mermaid --audience agent --json
jc render <run_id> --format html --audience lawyer --json
```

[有理有据的][高等] render先验证审计包的`COMPLETE`、文件hash和语义摘要，只消费既有`SemanticResult`与`Graph JSON`，不读取规则、不构造evaluator、不重新求值。

## 产物与绑定

[计算生成的][高等] 展示文件写入用户state root下的`renders/<run>/<result-digest>/<profile-hash>/`，不会修改不可变`runs/`审计包。每个正文旁均写同名`.render.json`，记录：

- result digest；
- renderer ID/version；
- profile ID/version/hash；
- audience、locale和format；
- 正文SHA-256；
- warnings和逻辑artifact ref。

[有理有据的][高等] 旁车元数据不重复正文，也不暴露本机绝对路径。

## Profile选择与权限

[计算生成的][高等] 优先级固定为：命令行`--profile`显式路径 > 用户私有`default.yaml` > 公共neutral profile。

- Windows私有默认：`%LOCALAPPDATA%\juris-calculus\profiles\default.yaml`；
- POSIX私有默认：`$XDG_CONFIG_HOME/juris-calculus/profiles/default.yaml`或`~/.config/juris-calculus/profiles/default.yaml`；
- 公共neutral：包内`configs/render_profiles/neutral.yaml`。

[有理有据的][高等] Profile只允许schema版本、ID/version、locale、tone、detail level、标题顺序与别名、引用显示偏好和禁用措辞。未知字段、结果字段、终局意见字段、缺失受保护章节、hash不符、换行/HTML标题或断言式终局措辞均fail closed。

## 不可改变的内容

[有理有据的][高等] Profile不能改变或隐藏：状态、结论ID、分支、来源、使用规则、使用事实、certificate种类、checker状态、风险、taint、复核标志和缺失事实。Markdown与HTML始终包含状态、结论、来源、风险和复核五个受保护章节。

[有理有据的][高等] Mermaid只把既有`graph.json`节点和显式边映射为图，不根据事件相邻顺序或自然语言生成新因果关系。HTML仅按用户明确命令生成，转义正文，设置禁用脚本和网络资源的CSP，不引入前端框架。

## 个人风格当前状态

[计算生成的][高等] 个人profile机制已经实现；个人风格内容仍为`BLOCKED`。当前仓库没有用户确认的5—10份写作样例、禁用表达和结构偏好，不能根据聊天记忆或项目文档猜测并宣称已校准。

[有理有据的][高等] 后续校准只提取表达特征，样例和私有profile不进入公共仓库；每次风格变更必须升级profile version/hash，且不能更新canonical golden。

## [我违规之处]

无。
