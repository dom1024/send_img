# `config.yaml` 配置手册

这份手册说明 [config.yaml](/Users/dom/github/send_img/config.yaml) 中每个字段的含义、默认行为、覆盖规则和常见用法。

程序启动时会读取 `config.yaml`，然后按以下流程工作：

1. 读取 `general` 全局配置。
2. 根据 `general.params` 和 `file_rules[*].params` 计算当日文件名规则。
3. 监听 `general.watch_dir`。
4. 文件落地并稳定后，按 `file_rules` 匹配。
5. 匹配成功后，按 `recipients` 和 `channels` 调用发送接口。

## 完整结构

```yaml
general:
  watch_dir: ./incoming
  recursive: true
  processed_base: .processed_files
  retry_count: 3
  retry_delay: 2
  stable_wait: 0.5
  stable_checks: 6
  case_insensitive: false
  ignore_office_temp: true
  retention_days: 30
  run_start: "06:00"
  run_stop: "23:59"

  delivery:
    url: "https://example.com/send"
    apply_id: "your_apply_id"
    sender: "your_sender"
    salt: "your_salt"
    receivers_type: "USER_ID"
    domain_code: "AR1"
    timeout: 30
    title: "{filename}"
    content: "请查收文件：{filename}"

  params:
    dt:
      type: date
      spec: "T-1"
      format: "%Y-%m-%d"
    region:
      type: string
      value: "CN"

file_rules:
  - name: "reportname_{dt}_{region}.png"
    recipients:
      - user_id: alice
        channels: [email]

  - name: "reportname_{dt}_{region}.xlsx"
    params:
      dt: "T-7"
    recipients:
      - user_id: bob
        channels: [chat]
```

## `general`

`general` 是全局配置区，控制监听行为、重试、清理、运行时间窗、发送接口默认值和模板参数。

### `general.watch_dir`

- 含义：监听目录。
- 类型：字符串。
- 示例：`./incoming`
- 行为：
  程序会自动创建这个目录。
- 建议：
  在 Linux 部署时尽量使用绝对路径，避免服务从不同工作目录启动时找不到目录。

### `general.recursive`

- 含义：是否递归监听子目录。
- 类型：布尔值。
- 示例：`true`
- 行为：
  - `true`：监听 `watch_dir` 下所有子目录。
  - `false`：只监听顶层目录。

### `general.processed_base`

- 含义：已处理记录文件的前缀。
- 类型：字符串。
- 示例：`.processed_files`
- 行为：
  程序每天会生成一个文件，例如：
  - `.processed_files_20260316.txt`
- 作用：
  避免同一个文件版本被重复发送。

### `general.retry_count`

- 含义：单次发送失败后的最大重试次数。
- 类型：整数。
- 示例：`3`
- 行为：
  每个 `recipient + channel` 组合都会独立重试。

### `general.retry_delay`

- 含义：重试间隔秒数。
- 类型：数字。
- 示例：`2`
- 行为：
  每次失败后等待指定秒数再重试。

### `general.stable_wait`

- 含义：文件稳定性检测的间隔秒数。
- 类型：数字。
- 示例：`0.5`
- 行为：
  用于判断文件是否写入完成。

### `general.stable_checks`

- 含义：文件稳定性检测次数。
- 类型：整数。
- 示例：`6`
- 行为：
  程序会连续检查文件大小；如果连续两次大小相同，则视为稳定。
- 组合含义：
  `stable_wait * stable_checks` 可以粗略理解为“最长等待文件稳定的时间窗口”。

### `general.case_insensitive`

- 含义：文件名匹配时是否忽略大小写。
- 类型：布尔值。
- 示例：`false`
- 行为：
  - `true`：`Report.PNG` 也可能匹配 `report.png`
  - `false`：严格区分大小写

### `general.ignore_office_temp`

- 含义：是否忽略 Office 临时文件。
- 类型：布尔值。
- 示例：`true`
- 行为：
  以 `~$` 开头的文件会被直接跳过。

### `general.retention_days`

- 含义：保留天数。
- 类型：整数。
- 示例：`30`
- 行为：
  程序会清理两类过期文件：
  - 监听目录中的旧数据文件
  - `processed_base_YYYYMMDD.txt` 这类旧处理日志
- 特殊值：
  - `0` 或负数：不清理

### `general.run_start`

- 含义：每天开始处理的时间。
- 类型：`HH:MM` 字符串。
- 示例：`"06:00"`

### `general.run_stop`

- 含义：每天停止处理的时间。
- 类型：`HH:MM` 字符串。
- 示例：`"23:59"`

### 时间窗说明

- 程序只会在 `run_start <= 当前时间 < run_stop` 的时间段内工作。
- 不在时间窗内时，watcher 会休眠。
- 配置格式错误时，会回退到默认值：
  - `run_start` 默认 `06:00`
  - `run_stop` 默认 `23:59`

注意：

- 当前实现不支持跨天时间窗。
- 例如 `23:00` 到 `06:00` 这种写法现在不能正常表示“夜间运行”。

## `general.delivery`

`general.delivery` 是发送接口的默认配置。除非在某个 `recipient` 中单独覆盖，否则发送时都使用这里的值。

### `general.delivery.url`

- 含义：上传接口地址。
- 类型：字符串。
- 必填：是
- 示例：`"https://example.com/send"`

### `general.delivery.apply_id`

- 含义：接口业务申请 ID。
- 类型：字符串。
- 必填：是
- 可被 `recipient.apply_id` 覆盖。

### `general.delivery.sender`

- 含义：发送方标识。
- 类型：字符串。
- 必填：是
- 可被 `recipient.sender` 覆盖。

### `general.delivery.salt`

- 含义：生成 `authBody` 时使用的盐值。
- 类型：字符串。
- 必填：是，除非你直接提供 `auth_body`
- 当前认证逻辑：
  - 先生成 `seqnum`
  - 再拼接 `apply_id + seqnum`
  - 再用 `salt` 进行 SM3 加密
  - 最终得到请求中的 `authBody`
- 可被 `recipient.salt` 覆盖。

### `general.delivery.receivers_type`

- 含义：请求体中的 `receiversType`。
- 类型：字符串。
- 必填：是
- 示例：`"USER_ID"`
- 可被 `recipient.receivers_type` 覆盖。

### `general.delivery.domain_code`

- 含义：请求头中的 `domainCode`。
- 类型：字符串。
- 默认值：`AR1`
- 示例：`"AR1"`

### `general.delivery.timeout`

- 含义：HTTP 请求超时时间，单位秒。
- 类型：数字。
- 默认值：`30`

### `general.delivery.title`

- 含义：消息标题模板。
- 类型：字符串。
- 默认值：`"{filename}"`
- 可用占位符：
  - `{filename}`：文件名，不带目录
  - `{filepath}`：文件绝对路径
  - `{channel}`：发送渠道
  - `{user_id}`：当前接收人配置中的 `user_id`

### `general.delivery.content`

- 含义：消息正文模板。
- 类型：字符串。
- 默认值：`"请查收文件：{filename}"`
- 可用占位符与 `title` 相同。

## `general.params`

`general.params` 是文件名模板的全局参数区。

例如：

```yaml
general:
  params:
    dt:
      type: date
      spec: "T-1"
      format: "%Y-%m-%d"
    region:
      type: string
      value: "CN"
```

配合：

```yaml
name: "report_{dt}_{region}.png"
```

当天如果是 `2026-03-16`，则会生成：

```text
report_2026-03-15_CN.png
```

### 支持的参数类型

#### `type: date`

日期类型参数支持：

- `spec: "T"`：当天
- `spec: "T-1"`：昨天
- `spec: "T-7"`：7 天前
- `spec: "2026-03-01"`：绝对日期

同时支持：

- `format: "%Y-%m-%d"`

#### `type: string`

示例：

```yaml
region:
  type: string
  value: "CN"
```

#### `type: number` 或 `type: int`

示例：

```yaml
batch_no:
  type: number
  value: 3
```

## `file_rules`

`file_rules` 是规则列表。程序会依次编译每条规则，并在文件到来时按文件名匹配。

### `file_rules[*].name`

- 含义：文件名模板。
- 类型：字符串。
- 必填：是

支持两类语法：

- 参数占位符：`{dt}`、`{region}`
- 通配符：
  - `*`：任意长度字符
  - `?`：单个字符

示例：

```yaml
name: "report_{dt}_{region}.png"
name: "daily_*_{dt}.jpg"
name: "img_????.png"
```

注意：

- 匹配的是文件名，不包含目录路径。
- 如果模板里引用了不存在的参数，这条规则会被跳过。

### `file_rules[*].params`

- 含义：规则级参数。
- 作用：覆盖 `general.params` 中的同名参数。

示例：

```yaml
general:
  params:
    dt:
      type: date
      spec: "T-1"
      format: "%Y-%m-%d"

file_rules:
  - name: "weekly_{dt}.png"
    params:
      dt: "T-7"
```

上面这个例子里，只有这一条规则的 `dt` 会变成 7 天前。

规则级简写也支持：

```yaml
params:
  dt: "T-7"
```

程序会自动把它理解成覆盖值。

### `file_rules[*].recipients`

- 含义：接收人列表。
- 类型：数组。
- 必填：建议填写；为空时规则虽然能匹配，但不会实际发送。

一个 `recipient` 可以包含以下字段。

## `recipient` 字段说明

### `recipient.user_id`

- 含义：接收人标识。
- 类型：字符串。
- 作用：
  - 如果未配置 `receivers`，默认会把它作为请求里的 `receivers`
  - 也会用于日志和模板占位符 `{user_id}`

### `recipient.channels`

- 含义：发送渠道列表。
- 类型：数组。
- 支持值：
  - `chat`
  - `email`

示例：

```yaml
channels: [chat]
channels: [email]
channels: [chat, email]
```

发送时会按数组逐个执行。

### `recipient.receivers`

- 含义：实际写入请求体 `receivers` 的值。
- 类型：字符串或数组。

示例 1，单值：

```yaml
receivers: alice
```

最终请求体：

```json
"receivers": "alice"
```

示例 2，多值：

```yaml
receivers: [alice, bob, carol]
```

最终请求体：

```json
"receivers": "alice,bob,carol"
```

注意：

- 当前实现会把数组拼成逗号分隔字符串。
- 如果接口要求的是 JSON 数组而不是逗号字符串，需要改代码。

### `recipient.receivers_type`

- 含义：覆盖全局 `general.delivery.receivers_type`
- 类型：字符串

### `recipient.apply_id`

- 含义：覆盖全局 `general.delivery.apply_id`
- 类型：字符串

### `recipient.sender`

- 含义：覆盖全局 `general.delivery.sender`
- 类型：字符串

### `recipient.salt`

- 含义：覆盖全局 `general.delivery.salt`
- 类型：字符串

### `recipient.auth_body`

- 含义：直接指定请求中的 `authBody`
- 类型：字符串
- 优先级：
  如果配置了它，程序将不再使用 `apply_id + seqnum + salt` 计算认证值。

### `recipient.title`

- 含义：覆盖全局 `general.delivery.title`
- 类型：字符串

### `recipient.content`

- 含义：覆盖全局 `general.delivery.content`
- 类型：字符串

## 字段覆盖优先级

发送相关字段的优先级如下：

1. `recipient` 中的字段
2. `general.delivery` 中的默认字段

也就是说，以下字段都支持“局部覆盖全局”：

- `apply_id`
- `sender`
- `salt`
- `auth_body`
- `receivers_type`
- `title`
- `content`

## 请求体生成规则

程序发请求时，会构造两块 JSON 字符串：

- `commonHeader`
- `body`

### `commonHeader`

```json
{
  "seqNum": "自动生成",
  "operatorId": "sender",
  "domainCode": "AR1",
  "authBody": "认证串"
}
```

### `body`

```json
{
  "applyId": "apply_id",
  "channels": "chat 或 email",
  "receivers": "alice,bob",
  "sender": "sender",
  "uploadType": "ims_image 或 email_file",
  "receiversType": "USER_ID",
  "params": "{\"title\": \"标题\", \"content\": \"正文\"}",
  "transmitParams": ""
}
```

### `uploadType` 对应关系

- `chat` -> `ims_image`
- `email` -> `email_file`

## 示例 1：最小可用配置

```yaml
general:
  watch_dir: /data/incoming
  recursive: true
  processed_base: /data/state/processed
  retry_count: 3
  retry_delay: 2
  stable_wait: 0.5
  stable_checks: 6
  case_insensitive: false
  ignore_office_temp: true
  retention_days: 30
  run_start: "06:00"
  run_stop: "23:59"

  delivery:
    url: "http://10.1.1.20:8080/send"
    apply_id: "A10001"
    sender: "system_robot"
    salt: "abc123"
    receivers_type: "USER_ID"

  params:
    dt:
      type: date
      spec: "T-1"
      format: "%Y-%m-%d"

file_rules:
  - name: "report_{dt}.png"
    recipients:
      - user_id: alice
        channels: [chat]
```

## 示例 2：一条规则发给多人

```yaml
file_rules:
  - name: "report_{dt}.png"
    recipients:
      - user_id: team_a
        receivers: [alice, bob, carol]
        channels: [email]
```

最终会把 `receivers` 写成：

```text
alice,bob,carol
```

## 示例 3：单个接收人覆盖默认标题和发送方

```yaml
general:
  delivery:
    sender: "default_sender"
    title: "默认标题 {filename}"
    content: "默认正文 {filename}"

file_rules:
  - name: "special_{dt}.png"
    recipients:
      - user_id: alice
        channels: [chat]
        sender: "special_sender"
        title: "专属消息"
        content: "请优先查看 {filename}"
```

## 常见注意事项

### 1. `run_start` 和 `run_stop` 不能跨天

当前实现不支持：

```yaml
run_start: "23:00"
run_stop: "06:00"
```

这种配置不会表示“夜间运行”。

### 2. 规则匹配的是文件名，不是全路径

例如目录里是：

```text
/data/incoming/sub/report_2026-03-15.png
```

实际参与规则匹配的是：

```text
report_2026-03-15.png
```

### 3. 成功发送后才会写入 processed 记录

如果发送失败，程序不会标记已处理，后续可能继续重试。

### 4. 同一个 `recipient` 配多个 `channels` 会发送多次

例如：

```yaml
channels: [chat, email]
```

程序会先走一次 `chat`，再走一次 `email`。

### 5. 如果字段缺失，会在发送阶段报错

以下字段缺失会导致发送失败：

- `general.delivery.url`
- `general.delivery.apply_id`
- `general.delivery.sender`
- `general.delivery.receivers_type`
- `recipient.user_id` 或 `recipient.receivers`
- `general.delivery.salt`，除非你显式配置了 `auth_body`

## 推荐做法

- Linux 部署时使用绝对路径。
- 先在测试目录里放一个样例文件，确认文件名是否能匹配规则。
- 先只配一个 `recipient` 和一个 `channel`，联通后再扩展。
- 如果要发多人，先确认接口是否接受逗号分隔字符串。
- 如果接口返回中有业务状态码，建议后续把“成功判定”从只看 HTTP 200 升级为解析返回体。
