# codex-watchsmith

**오래 걸리는 Codex 작업의 진행 상태와 완료 알림을 모바일로 받아보세요.**

`codex-watchsmith`는 다음 세 가지를 조합합니다.

- **ActivitySmith MCP + 전역 `AGENTS.md`**: Codex가 장기 작업 여부를 스스로 판단하고 의미 있는 Live Activity를 전송합니다.
- **Codex `notify` dispatcher**: 기존 Computer Use 등의 notifier를 보존하면서 작업 완료 Push를 추가합니다.
- **60초 외부 watchdog**: `codex exec` 작업이 오래 걸리는데 에이전트가 알림을 놓친 경우 fallback 알림을 보냅니다.

macOS 우선 지원입니다.

[English README](README.md)

## 왜 필요한가요?

`AGENTS.md`에 “60초가 넘으면 알림을 보내라”고 적어도 그 지침은 타이머가 아닙니다. Codex가 긴 tool call이나 shell command 안에서 대기 중이면 정확히 60초 시점에 다시 제어권을 얻지 못할 수 있습니다.

Watchsmith는 역할을 나눕니다.

```text
Agent / MCP   = 의미 있는 상태 전달
                예: 테스트 실행 중, 오디오 렌더링 중

Watchdog      = 시간 기반 안전망
                예: 60초 이상 프로세스가 살아 있음

notify hook   = 작업 완료 이벤트
```

## 빠른 설치

```bash
git clone https://github.com/<YOUR_GITHUB>/codex-watchsmith.git
cd codex-watchsmith
./install.sh

npm i -g activitysmith-cli@latest
echo 'export PATH="$HOME/.codex/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

activitysmith-keychain-setup
activitysmith-test
```

설치 후 Codex를 완전히 종료했다가 다시 실행하세요.

ActivitySmith MCP는 별도로 Codex에 연결되어 있어야 합니다. MCP는 진행 상태를 의미 있게 전달하는 데 사용하고, CLI/API Key는 외부 notifier와 watchdog에서 사용합니다.

## 설치 프로그램이 하는 일

설치 후 구조는 대략 다음과 같습니다.

```text
~/.codex/
├── AGENTS.md
├── config.toml
├── bin/
│   ├── codex-watch
│   ├── activitysmith_notify.py
│   ├── watchsmith_notify_dispatcher.py
│   ├── activitysmith-keychain-setup
│   └── activitysmith-test
└── watchsmith/
    ├── previous_notify.json
    └── config.toml.backup.*
```

기존 `config.toml`에 top-level `notify`가 존재하면 installer가 argv를 `previous_notify.json`에 보존합니다.

그다음 Codex의 notifier는 Watchsmith dispatcher로 연결됩니다.

```toml
notify = ["python3", "/Users/you/.codex/bin/watchsmith_notify_dispatcher.py"]
```

작업 완료 시 흐름은 다음과 같습니다.

```text
Codex agent-turn-complete
        │
        ▼
 Watchsmith dispatcher
   ├─ 기존 notifier 실행
   └─ ActivitySmith 완료 Push
```

따라서 기존 Computer Use notifier와 Watchsmith를 함께 사용할 수 있습니다.

## Codex 공통 지침

installer는 [`config/activitysmith-agents.md`](config/activitysmith-agents.md)의 내용을 `~/.codex/AGENTS.md`에 한 번만 추가합니다.

기본 판단 기준은 다음과 같습니다.

- 약 1분 이상 걸릴 가능성이 있으면 ActivitySmith 사용을 적극 고려
- 여러 단계 또는 여러 tool call이 필요한 작업이면 ActivitySmith 사용
- 처음에는 짧은 작업으로 판단했더라도 1분 이상 진행되면 ActivitySmith로 승격
- 의미 있는 진행 변화는 Live Activity
- 완료, 실패, blocker, 사용자 입력 필요 시 Push
- prompt 전문, credential, 고객 데이터, 소스코드 전문, 회사 기밀은 ActivitySmith로 보내지 않음

설치 후 정책을 바꾸고 싶다면 다음 파일을 수정하세요.

```text
~/.codex/AGENTS.md
```

## 60초 watchdog 사용

한 번 실행되고 종료되는 Codex 작업은 다음처럼 감쌀 수 있습니다.

```bash
codex-watch codex exec "전체 테스트를 실행하고 실패 원인을 수정해"
```

기본 threshold는 60초입니다.

테스트 목적으로 10초로 줄이려면:

```bash
CODEX_WATCH_THRESHOLD_SECONDS=10 \
  codex-watch codex exec "여러 단계의 분석 작업을 수행해"
```

설치된 ActivitySmith CLI가 다음 명령을 지원하면:

```bash
activitysmith activity stream
```

watchdog fallback은 Live Activity를 사용합니다.

지원하지 않으면 자동으로 Push 알림으로 fallback합니다.

Codex 내부의 ActivitySmith MCP Live Activity는 이 CLI 기능과 별개이므로 계속 사용할 수 있습니다.

## 기존 Computer Use notifier와 함께 사용하기

기존 설정이 예를 들어 다음과 같아도:

```toml
notify = ["/path/to/SkyComputerUseClient", "turn-ended"]
```

installer가 기존 argv를 보존한 뒤 dispatcher로 교체합니다.

```text
Codex
  └─ Watchsmith dispatcher
      ├─ SkyComputerUseClient ... <payload>
      └─ ActivitySmith 완료 Push
```

따라서 기존 Computer Use 알림 동작을 유지하면서 ActivitySmith 알림을 추가할 수 있습니다.

## 보안

ActivitySmith API Key는 macOS Keychain의 다음 service 이름으로 저장합니다.

```text
activitysmith-codex
```

API Key를 `.zshrc`, `config.toml`, 저장소 파일에 직접 기록하지 않습니다.

완료 notifier는 Codex가 넘겨주는 payload 중 사용자 prompt나 assistant 응답 본문을 ActivitySmith로 전달하지 않습니다. 기본적으로 generic completion signal만 전송합니다.

또한 전역 Codex 지침에서는 다음 내용을 ActivitySmith로 보내지 않도록 요구합니다.

- API key, token, password
- 개인정보
- 고객 데이터 및 고객 식별정보
- 전체 소스코드 또는 긴 코드 조각
- 회사 기밀
- 계약/재무/영업 비공개 정보
- 내부 URL, IP, credential
- 원본 문서·음원 내용
- prompt 전문

## 설치 확인

```bash
activitysmith-test
grep '^notify' ~/.codex/config.toml
which codex-watch
```

정상 설치 시 notifier는 대략 다음 형태입니다.

```text
notify = ["python3", ".../.codex/bin/watchsmith_notify_dispatcher.py"]
```

그다음 Codex에서 짧은 작업 하나를 완료해 ActivitySmith 완료 Push가 오는지 확인하세요.

## 현재 구조

```text
                       ~/.codex/AGENTS.md
                               │
                               ▼
                       ActivitySmith MCP
                    의미 있는 진행 상태 전달
                               │
                               ▼
                             iPhone
                               ▲
                ┌──────────────┴──────────────┐
                │                             │
      notify dispatcher                 codex-watch
      작업 완료 Push                    60초 fallback
                │                             │
        기존 notifier 보존                codex exec
```

자세한 내용은 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)를 참고하세요.

## 알려진 제약사항

- `codex-watch`는 `codex exec`처럼 한 번 실행되고 종료되는 프로세스에 가장 적합합니다.
- 계속 켜두는 interactive Codex TUI 전체를 `codex-watch codex`로 감싸면 개별 turn이 아니라 프로세스 전체 수명을 보게 됩니다.
- Desktop/Work에서 정확한 60초 task-start fallback을 구현하려면 안정적인 task-start event surface가 필요합니다. 현재는 ActivitySmith MCP + 전역 지침을 우선 사용합니다.
- ActivitySmith CLI 버전에 따라 `activity stream` 지원 여부가 다를 수 있으며 Watchsmith는 이를 감지해 Push fallback을 사용합니다.

## 문제 해결

### `unknown command 'stream'`

치명적인 오류는 아닙니다. 현재 ActivitySmith CLI에 `activity stream`이 없다면:

- MCP Live Activity는 계속 사용 가능
- 외부 60초 watchdog은 Push fallback 사용

확인:

```bash
activitysmith --version
activitysmith activity --help
```

### `nice(5) failed: operation not permitted`

현재 Watchsmith 스크립트는 zsh의 `BG_NICE`를 비활성화합니다. 이전 버전이 설치되어 있다면 재설치하세요.

### `read-only variable: status`

현재 버전은 zsh 특수 변수 `status`를 사용하지 않고 `exit_code`를 사용합니다.

### 기존 notifier 확인

```bash
cat ~/.codex/watchsmith/previous_notify.json
grep '^notify' ~/.codex/config.toml
```

### API Key 확인

```bash
security find-generic-password \
  -a "$USER" \
  -s activitysmith-codex \
  -w >/dev/null && echo OK
```

## 삭제

```bash
./uninstall.sh
```

가능하면 기존 notifier를 복원하고 Watchsmith 실행 파일을 제거합니다.

`AGENTS.md`에 추가된 tagged block과 Keychain의 API Key는 사용자가 직접 검토할 수 있도록 자동 삭제하지 않습니다.

## License

MIT

## 설치 안전성 및 로컬 테스트

TOML 검증을 위해 Python 3.11 이상이 필요합니다. `CODEX_HOME`을 지원하며 기본값은 `~/.codex`입니다. 설치된 dispatcher는 자신의 위치를 기준으로 상태 파일과 notifier를 찾으므로 GUI 프로세스가 `CODEX_HOME`을 전달하지 않아도 동작합니다.

installer는 전체 TOML을 검증한 뒤 최상위 `notify`만 교체합니다. 여러 줄 배열과 따옴표로 감싼 키를 지원하며 중첩 설정은 유지합니다. 잘못된 TOML이나 문자열이 아닌 notify 인수가 있으면 설정을 수정하지 않고 중단합니다. 백업 이름은 중복되지 않으며 설정 파일은 원자적으로 교체합니다. 동일한 dispatcher를 재설치하면 기존 notifier 기록을 보존합니다. 기존 notifier가 없었던 경우 JSON `null`을 저장합니다. 복원 정보가 없으면 추측해서 덮어쓰지 않고 재설치·제거를 중단합니다.

제거 시 최상위 notifier가 이 설치의 dispatcher인 경우에만 이전 인수 배열을 복원합니다. 사용자가 변경한 notifier는 유지합니다. notify의 표기 형식은 정규화될 수 있으며 원문은 백업에 남습니다. 전역 정책 갱신과 설치 전체의 롤백은 아직 후속 작업입니다.

실제 Codex 설정을 변경하거나 알림을 보내지 않는 회귀 테스트:

```bash
python3 -m unittest discover -s tests -v
```

테스트는 설치·제거, 기록용 notifier로의 정확한 인수 전달, 모의 CLI를 이용한 일반 완료 명령 구성을 검증합니다. 실제 Computer Use 클라이언트, Codex 이벤트 발생, 모바일 수신을 검증한 것은 아닙니다.
