# 榆巷剧场排练灯光服务

排练领队在控台校样开场灯光，现场灯光员可直接操作灯台，交班员根据实际出光流水复盘。服务在本机运行，使用 Python 3.11 标准库。控台和灯台各用一份 SQLite 库。

## 运行

```sh
python3 -B -m rehearsal.application lamp --db lamp.sqlite --port 8766
python3 -B -m rehearsal.application console --db console.sqlite --port 8765 --lamp-url http://127.0.0.1:8766
```

分别启动两条命令。进程监听 `127.0.0.1`，启动后打印 `READY` 和实际基址。`--port 0` 由操作系统选端口。再次启动时沿用已有场景、编号、实显和复盘。启动只补建库结构。样例和测试各自使用临时目录。

```sh
python3 -B demo.py
python3 -B demo.py --incident
python3 -B check_project.py
```

最后一条命令使用平台物化时提供的检查入口。直接运行标准库发现也可执行原套件，命令为 `python3 -B -m unittest discover -s tests -t . -v`。

## 一个班次

领队登记 `F1`，保存 `opening` 草稿并把 80 校为第一版。改稿到 30 后可发布第二版，随后仍可按第一版开练。轮次 `R1` 的 `F1` 初始实显 80。控台 `A` 加 30 后实显 100，现场 `L` 加 10 后仍实显 100，控台 `C` 减 10 后实显 90。控台 `W` 撤去 `A` 后实显 80。交班复盘保留全部五次实显及其来源，包括 `A` 当时的 100。

## JSON HTTP

POST 使用 JSON 对象。GET 使用表中的查询参数。标识是非空字符串。初值是 0–100 的整数，增量是有符号整数，布尔值不作整数使用。亮度单位为整数级。

| 服务 | 方法与路径 | 请求字段 | 成功结果 |
| --- | --- | --- | --- |
| 控台 | POST `/fixture` | `fixture`, `label` | 灯位登记，同号同名可重投 |
| 控台 | GET `/fixture` | `fixture` | 灯位登记 |
| 控台 | POST `/draft` | `scene`, `levels`（灯位到待校值的对象） | 当前场景稿 |
| 控台 | GET `/draft` | `scene` | 当前场景稿 |
| 控台 | POST `/proof` | `scene` | `edition`, `scene`, `levels` |
| 控台 | GET `/edition` | `edition` | 固定场景版及校样值 |
| 控台 | POST `/open` | `session`, `edition` | 轮次、所选版、`bindings` 和 `initial` |
| 控台 | POST `/adjust` | `session`, `fixture`, `action`, `delta` | 首执或待查 |
| 控台 | POST `/withdraw` | `session`, `fixture`, `action`, `target` | 首执或待查 |
| 控台 | GET `/receipt` | `session`, `action` | 控台首执或待查 |
| 灯台 | POST `/local` | `session`, `fixture`, `action`, `delta` | 本地动作首执 |
| 灯台 | GET `/current` | `session`, `fixture` | 当前实显事实 |
| 灯台 | GET `/first` | `session`, `source`, `action` | 指定首执，来源为 `desk`、`local` 或 `initial` |
| 控台 | POST `/close` | `session` | `session`, `report` |
| 控台 | GET `/report` | `report` | `session`, `edition`, `cutoff`, `timeline`, `sources` 和复盘号 |

保存草稿可保留待校值。校样检查整稿后才发行固定版，失败后仍可按旧版开练。同轮同版重开返回最初一组实显。灯位号按字符串排序后登记初始实显，初始事实的动作号为灯位号。实显事实有 `session`、`fixture`、`seq`、`source`、`kind`、`action`、`level` 和 `target`，只有撤去事实带非空 `target`。调光首执另带原 `delta`。控台已核首执另带 `status: applied`，待查返回 `session`、`action` 和 `status: pending`。

灯台按实显序接纳动作。每次先加增量，再截到 0–100。撤去的目标须为同轮同灯位的控台调光。灯台从固定初值按原序逐步应用仍有效的增量，饱和处和零增量同样保留。再次用新号撤去同一动作仍产生一笔具名实显，有效历史中只排除该目标一次。旧实显和原号首执始终保留。

控台和灯台各自提交。控台办理结果未知时返回 HTTP 202。原号同参重投可续办或领取首次结果。`receipt` 会查证灯台原号，若现场尚无可查首执则继续待查。调光、撤去、现场动作的复领均不改变现值。控台号和本地号分别在其来源下按轮次分配；控台调光和撤去共用控台号。相同号改种类、灯位、增量或撤去目标返回 409。无效字段或校样返回 400，未知资源或撤去目标返回 404，已封轮的新动作返回 409。响应错误体含 `error`。开练确认和收尾核对暂时不可用时返回 503，可用原轮次继续。

收尾登记后控台停止受理新动作。灯台在同一个现场事务边界封轮，截定最后实显，并继续提供现值和原号读取。控台核齐截止流水后关轮和封册。原轮次重投 `/close` 复领同一个复盘号，原册保留当时每次实显和来源。部署时控台的灯台基址指向本机灯台服务。
