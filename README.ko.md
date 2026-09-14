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

## 설치 전 준비사항

Watchsmith는 이미 사용하는 Codex에 알림 기능을 연결하는 애드온입니다. 설치 프로그램은 Codex·Python·Node.js·ActivitySmith 설치, 계정 생성, MCP 연결을 대신하지 않습니다. 아래 사항을 준비한 뒤 빠른 설치를 진행하세요.

### 1. Mac 실행 환경 준비

- **macOS와 zsh:** 설치·실행 스크립트는 zsh와 macOS Keychain을 사용합니다.
- **정상 작동하는 Codex:** 로그인하고 간단한 작업이 완료되는지 먼저 확인하세요. `codex-watch codex exec`를 사용하려면 Codex CLI도 설치해야 합니다. Desktop 앱만으로 해당 명령이 제공되는 것은 아닙니다.
- **Python 3.11 이상:** 터미널에서 `python3`를 실행할 수 있어야 합니다. Python이나 TOML 파서를 찾지 못하면 설치가 중단됩니다.
- **Node.js와 npm:** 아래 명령으로 ActivitySmith CLI를 설치하고 실행하는 데 필요합니다. CLI의 실행 환경 요구사항은 [ActivitySmith CLI 공식 안내](https://activitysmith.com/sdks/cli)를 참고하세요.
- **저장소 파일:** 빠른 설치 예시는 Git을 사용합니다. Git이 없다면 저장소 ZIP을 다운로드·압축 해제한 뒤 해당 폴더에서 터미널을 열고 `./install.sh`부터 진행할 수 있습니다.

터미널에서 준비 상태를 확인하세요.

```bash
python3 --version   # 3.11 이상이어야 합니다
node --version
npm --version
# CLI watchdog 사용 시 필요하며, Desktop만 사용한다면 생략 가능합니다:
codex --version
```

필요한 명령을 찾을 수 없으면 해당 도구부터 설치하세요. 현재 Watchsmith 설치기는 Python만 자동 검사하며, 모든 사전 조건을 검사하지는 않습니다.

### 2. ActivitySmith 계정·수신 기기·API Key 준비

[ActivitySmith 공식 시작 안내](https://activitysmith.com/quickstart)에 따라 다음을 완료하세요.

1. ActivitySmith 계정을 만들거나 기존 계정으로 로그인합니다.
2. ActivitySmith iOS 앱을 설치하고 알림을 받을 기기를 해당 계정에 연결합니다. 알림 권한을 허용하고, Live Activity를 사용할 경우 해당 기능도 활성화합니다.
3. 같은 계정의 ActivitySmith 웹 앱에서 API Key를 발급합니다. Watchsmith 설치 후 `activitysmith-keychain-setup`에서 입력하면 macOS Keychain에 저장됩니다. 키를 저장소나 Codex 설정 파일에 붙여 넣지 마세요.
4. ActivitySmith Playground에서 테스트 알림을 보내 실제 기기에 표시되는지 먼저 확인합니다. 이 단계가 완료돼야 Watchsmith 연결 문제와 기기 수신 문제를 구분할 수 있습니다.

Mac에는 CLI 설치와 알림 전송을 위한 인터넷 연결이 필요하며, 수신 기기도 알림을 받을 수 있는 상태여야 합니다. 계정 생성과 API Key 발급만으로 기기 설정까지 끝나는 것은 아닙니다.

### 3. 작업 단계별 진행 알림을 사용하려면 MCP 연결

Codex가 ActivitySmith 도구로 작업 단계와 진행 상황을 알리게 하려면, [ActivitySmith MCP 공식 설정 안내](https://activitysmith.com/integrations/mcp-server)의 Codex 연결 절차에 따라 별도로 연결하고 인증을 완료하세요. 새 Codex 세션에서 ActivitySmith 도구를 사용할 수 있는지 확인합니다.

MCP 인증과 CLI용 API Key는 별개입니다. MCP는 에이전트가 직접 보내는 진행 알림에 필요하며, 완료 notifier와 CLI watchdog만 사용할 때는 필수가 아닙니다. 전역 에이전트 지침을 추가하는 것만으로 MCP가 연결되지는 않습니다.

### 4. 설치 위치 확인

기본 설치 위치는 `~/.codex`입니다. 다른 위치의 Codex 설정을 사용한다면 설치 전에 `CODEX_HOME`을 해당 디렉터리로 지정하고, 재설치·제거에도 같은 값을 사용하세요. 아래 기본 경로 대신 해당 디렉터리의 `bin` 폴더를 명령 검색 경로에 추가해야 합니다.

기존 `notify` 설정은 미리 삭제할 필요가 없습니다. 설치기가 보존한 뒤 dispatcher를 통해 이벤트를 전달합니다. 다만 기존 Computer Use 호환성은 아직 검증 중입니다. 최근 검사에서 해당 notifier의 시간 초과가 발생했으므로, 설정 보존을 실제 정상 작동 확인과 동일하게 보지는 않습니다.

설치 프로그램의 완료 메시지는 로컬 파일과 설정의 설치가 끝났다는 뜻입니다. 아래의 CLI 설치, 명령 경로 등록, Keychain 등록, 연결 테스트, Codex 재시작까지 마쳐야 알림 설정이 완료됩니다.

## 빠른 설치

```bash
git clone https://github.com/GrooshBene/codex-watchsmith.git
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
