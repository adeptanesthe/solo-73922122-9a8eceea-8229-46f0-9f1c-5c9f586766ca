# 干扰峰复测档位诊断（Flask + Docker Compose）

调音师输入至多 32 个整数 Hz 的疑似干扰频率、已测各采样率档位的完整峰表，以及可用复测采样率。系统枚举所有含 1～4 个频率的候选组合，按采样率混叠折叠后与每次实测峰表做**无序集合的精确一致**校验，并给出：

- 全部可行候选组合；
- **必有频率**：出现在每个可行组合中；
- **仅可能有频率**：只出现在部分可行组合中；
- 附加标出“所有组合均不含”的可排除频率；
- 多个组合时，推荐数值最低的、能让所有当前候选在一次新测量后得到互不相同峰表的可用采样率；
- 若没有任何可用档位能区分全部组合，明确提示“无合适档位”；
- 补录峰表时先做约束叠加；若叠加后无解，API 返回 `409` 和补录前原结果，不接受该补录。

## 混叠与判定规则

对源频率 `f` 和采样率 `sr`：

```text
r = f mod sr
alias(f, sr) = min(r, sr - r)     # 0 <= alias <= sr / 2
```

同一候选中多个频率折到同一峰时只保留一个峰。候选峰表排序去重后，必须与每次实测的完整峰表完全相同：不能缺峰，也不能多峰。

最大候选规模为：

```text
C(32,1) + C(32,2) + C(32,3) + C(32,4) = 41,448
```

纯 Python 诊断核心在 `diagnostics.py`，不依赖 Flask，便于测试和复用。

## 文件内容

| 路径 | 内容 |
| --- | --- |
| `app.py` | Flask 页面与 JSON API：`/api/analyze`、`/api/supplement`、`/api/example`、`/api/health` |
| `diagnostics.py` | 整数校验、混叠折叠、组合枚举、频率标注、最低分辨档位推荐、补录拒绝逻辑 |
| `examples.py` | 内置演示数据及有效/矛盾补录峰表 |
| `templates/index.html` | 单页界面结构 |
| `static/app.js` | 动态档位输入、诊断渲染、补录交互、`409` 后保留原结果 |
| `static/style.css` | 响应式样式，无外部 CDN/前端构建依赖 |
| `tests/test_diagnostics.py` | 混叠、组合、推荐、补录拒绝、边界和规模测试 |
| `tests/test_app.py` | Flask 页面与 API 端到端测试 |
| `Dockerfile` | Python 3.11 slim + Gunicorn，非 root 运行 |
| `docker-compose.yml` | `web` 服务、端口映射、健康检查；可用 `WEB_PORT` 改宿主端口 |

## Docker Compose 启动

```bash
docker compose up --build
```

打开：

```text
http://localhost:8000
```

如宿主 `8000` 端口被占用：

```bash
WEB_PORT=18080 docker compose up --build
# 打开 http://localhost:18080
```

停止：

```bash
docker compose down
```

健康检查：

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

## 本地直接试跑

环境需要 Python 3.11+：

```bash
python -m pip install -r requirements.txt
python app.py
# 或：gunicorn --bind 0.0.0.0:8000 app:app
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 内置网页演示

打开页面后会自动载入内置示例，也可点击右上角“载入内置示例”。

示例疑似频率：

```text
[1700, 3900, 9400, 11200, 14000, 14700, 17400, 18300] Hz
```

已测 `8000 Hz` 档位完整峰表：

```text
[1400, 2000, 2300] Hz
```

`9400` 和 `17400 Hz` 在 `8000 Hz` 下都折到 `1400 Hz`，因此初始有 3 个可行组合：

```text
[9400, 14000, 18300]
[14000, 17400, 18300]
[9400, 14000, 17400, 18300]
```

标注结果：

- 必有：`14000`、`18300 Hz`
- 仅可能有：`9400`、`17400 Hz`
- 可排除：其余 4 个频率

可用档位为 `[11025, 12000, 16000, 22050, 48000] Hz` 时，推荐最低档位 `11025 Hz`。三个候选在该档位分别得到：

```text
[1625, 2975, 3750]
[2975, 3750, 4650]
[1625, 2975, 3750, 4650]
```

网页操作：

1. 在“补录峰表”中点“填入有效演示峰表”，提交后诊断收敛为唯一组合 `[9400, 14000, 17400, 18300] Hz`，推荐变为“无需复测”。
2. 重新载入内置示例，点“填入矛盾演示峰表”并提交；后端返回 `409`，页面提示拒绝原因，且继续显示原来的 3 个候选。
3. 点输入区的“演示‘无合适档位’提示”，可用档位会改成 `8000 Hz`；由于所有候选在该已测档位的峰表相同，页面显示“无合适复测档位”和各档位碰撞情况。

## JSON API 示例

### 诊断

```bash
curl -s http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "suspects": [1700, 3900, 9400, 11200, 14000, 14700, 17400, 18300],
    "observations": [
      {"sample_rate": 8000, "peaks": [1400, 2000, 2300]}
    ],
    "available_rates": [11025, 16000, 48000]
  }'
```

主要响应字段：

```json
{
  "feasible": true,
  "candidate_count": 3,
  "candidates": [
    {"frequencies": [9400, 14000, 18300]}
  ],
  "mandatory_frequencies": [14000, 18300],
  "possible_only_frequencies": [9400, 17400],
  "excluded_frequencies": [1700, 3900, 11200, 14700],
  "recommendation": {
    "status": "recommended",
    "sample_rate": 11025,
    "signatures": []
  }
}
```

`recommendation.status` 可能为：

- `recommended`：存在最低可分辨档位；
- `already_unique`：当前组合已唯一，无需复测；
- `no_suitable_gear`：有多个组合，但所有可用档位均有碰撞；
- `no_candidates`：当前数据无解。

### 补录

请求把原案例字段和 `new_observation` 一起提交：

```bash
curl -i http://localhost:8000/api/supplement \
  -H 'Content-Type: application/json' \
  -d '{
    "suspects": [9400, 14000, 17400, 18300],
    "observations": [
      {"sample_rate": 8000, "peaks": [1400, 2000, 2300]}
    ],
    "available_rates": [11025],
    "new_observation": {
      "sample_rate": 11025,
      "peaks": [1625, 2975, 3750, 4650]
    }
  }'
```

- 补录可行：`200`，响应中 `supplement_accepted: true` 和更新后的完整诊断。
- 补录无解：`409`，响应形如 `{"accepted": false, "error": "...", "original": {...补录前完整诊断...}}`。
- 输入不是整数、超过 32 个疑似频率或峰超过 Nyquist：`400`，带字段级 `issues`。

也支持 `{"case": { ... }, "new_observation": { ... }}` 的包装形式。

## 交付前试跑记录

以下结果来自当前交付环境（Python 3.11.2；交付时代码已实际运行）：

```text
python3 -m unittest discover -s tests -v
Ran 17 tests in 0.205s

OK
```

覆盖：

- 混叠到 `0～sr/2`、倍采样率点和 Nyquist 点；
- 重合峰去重；
- 内置示例的 3 个候选、必有/仅可能有频率；
- 最低推荐档位 `11025 Hz` 及签名互异；
- 无合适档位；
- 有效补录收敛为唯一组合；
- 矛盾补录抛出 `NoSolutionError` 并携带原结果；
- 32 个频率下 `41,448` 个组合的枚举规模；
- Flask 首页、健康检查、示例、分析、补录成功/`409`/输入校验 API。

其他已执行核对：

```text
node --check static/app.js
JS_SYNTAX_OK

使用 PyYAML 解析 `docker-compose.yml`：

```text
docker-compose.yml OK interference-gear-advisor:latest ['${WEB_PORT:-8000}:8000'] healthcheck=True

git diff --check
GIT_DIFF_CHECK_OK
```

实际启动过 Flask 开发服务器和与 Docker 命令一致的 Gunicorn：

```text
GET /api/health                 -> {"status":"ok"}
GET /                           -> 200，标题正确
GET /static/app.js              -> 200
GET /static/style.css           -> 200
POST /api/analyze（内置示例）    -> 200，candidates=3，recommend=11025
POST /api/supplement（矛盾峰表） -> 409，accepted=false，original=3
POST /api/supplement（有效峰表） -> 200，candidates=1
Gunicorn 127.0.0.1:8001         -> /api/health 与 /api/analyze 验证通过
```

另在临时目录用 jsdom 加载真实 HTML/JS 并连接上述 API 做了事件级冒烟：

```text
initial candidates/recommendation -> 3 / 11025 Hz
矛盾补录后 candidate count        -> 3，观测行仍为 1（未追加）
有效补录后 candidate count        -> 1，观测行变为 2
“无合适档位”演示                  -> 正确显示“无合适复测档位”
UI_SMOKE_OK
```

## 假设、限制与余项

1. 频率和采样率按物理非负整数 Hz 处理；疑似频率允许 `0 Hz`，负数不接受。实测峰必须位于 `0 <= peak <= sr/2`。
2. 峰表视为无序、唯一峰集合；重复录入会去重并给出 warning。候选内混叠重合也只算一个峰。
3. 判定是精确整数匹配，没有加入测量误差、频偏容差或漏峰/假峰概率模型；这与题目“完全一致”一致。
4. 推荐只保证“当前仍可行的候选组合”在新档位下两两不同。已被旧实测排除的组合不再参与分辨要求。
5. 页面候选卡片和签名表最多预览前 50 条，避免无观测时一次渲染数万张 DOM 卡片；`/api/analyze` JSON 仍返回全部候选和推荐签名。
6. 当前环境没有 `docker` / `docker compose` 可执行程序，因此未能在此环境真正执行 `docker compose up --build`；已验证等价的 Gunicorn 启动命令。Compose 文件和 Dockerfile 已按标准 Python 镜像编写，留待有 Docker daemon 的环境首次构建确认。
7. 未做真实 Chromium/Firefox 像素级视觉验收；已通过 `node --check`、元素 ID 核对和 jsdom 事件级冒烟（初始渲染、有效补录、`409` 拒绝且不追加观测行、无档位提示）。
