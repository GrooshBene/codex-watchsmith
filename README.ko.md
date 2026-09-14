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
  `watchsmith` 명령은 기본 `python3`가 구버전이어도 PATH와 macOS의 일반적인 설치 위치에서 Python 3.11 이상을 찾아 실행합니다. 호환되는 Python이 없으면 설치 안내를 표시합니다.
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

## 설치 도우미 (v0.2.0 이상)

설치 도우미가 포함된 저장소 또는 릴리스 패키지에서 `./setup.sh`를 실행하면 됩니다. 필요한 환경을 확인하고, 없는 CLI 설치·기존 설정 보존·Keychain 등록·명령 경로 설정·테스트 알림을 순서대로 안내합니다. 이미 준비된 항목은 재사용합니다.

설치 후에는 `watchsmith setup`으로 건너뛴 단계를 이어가고, `watchsmith doctor` 또는 `watchsmith doctor --json`으로 로컬 상태를 진단합니다. 진단은 설정을 바꾸거나 알림을 보내지 않으며, 키·설정 원문을 출력하지 않습니다.

macOS와 Python 3.11+는 필요합니다. 계정·기기 연결과 MCP 인증은 안내에 따라 직접 완료합니다. 단일 명령 다운로드 진입점은 v0.2.0부터 제공하며, v0.1.0에는 없습니다. [설치 도우미 상세 안내](docs/SETUP.md)를 참고하세요. 아래 수동 설치 방식도 계속 지원합니다.

## 신규 설치

이미 설치했거나 레거시 버전을 사용 중이라면 아래 **기존 컴퓨터 업그레이드** 절차를 따르세요. 먼저 삭제하거나 기존 `notify` 설정을 지울 필요가 없습니다.

1. 위 사전 준비를 마친 뒤 저장소를 내려받고 설치합니다.

```bash
git clone https://github.com/GrooshBene/codex-watchsmith.git
cd codex-watchsmith
npm i -g activitysmith-cli@latest
./install.sh --check
./install.sh
```

2. 아래 줄을 `~/.zshrc`에 **한 번만** 추가하고 새 터미널을 여세요. 사용자 지정 `CODEX_HOME`을 쓴다면 설치 때와 같은 값을 유지합니다.

```bash
export PATH="${CODEX_HOME:-$HOME/.codex}/bin:$PATH"
```

3. API 키를 Keychain에 저장하고 CLI 연결을 확인합니다.

```bash
activitysmith-keychain-setup
activitysmith-test
```

4. 작업 단계별 진행 알림이나 상세 결과가 필요하면 ActivitySmith MCP 인증도 별도로 완료합니다. Codex를 재시작하고 새 작업을 시작해야 변경된 전역 지침과 notify 설정을 읽습니다.
5. 짧은 작업을 완료해 휴대폰 알림을 확인합니다. 진행 알림 조율을 사용하려면 `codex-watch codex exec "작업 내용"`으로 실행하세요. Desktop을 여는 것만으로 이 watchdog이 시작되지는 않습니다.

`--check`는 파일을 바꾸지 않습니다. 설치기는 복구 기록을 남기고 기존 notifier를 보존합니다. 로컬 설치 성공과 실제 휴대폰 수신 확인은 별개입니다.

## 기존 컴퓨터 업그레이드

업데이트된 저장소 파일과 **기존 설치 위치**를 사용합니다. 수정 사항이 없는 Git 작업 폴더에서는 `git pull --ff-only`로 공개된 업데이트를 받을 수 있습니다. 로컬 변경이 있다면 먼저 보존하세요.

```bash
cd /path/to/codex-watchsmith
# 사용자 지정 위치를 쓰는 경우에만 기존 CODEX_HOME을 먼저 지정합니다.
./install.sh --check
```

진행 중인 Codex/watchdog 작업을 마치고 관련 앱을 닫은 뒤, 별도 터미널에서 실행합니다.

```bash
./install.sh --upgrade --quiesced
./install.sh --check
```

두 번째 점검의 `changes`가 빈 배열이면 설치 파일이 현재 저장소와 일치합니다. `--quiesced`는 관련 작업이 멈췄다는 사용자의 확인이며, 프로세스를 자동 종료하는 옵션은 아닙니다.

dispatcher, 완료 전송 기록, 결과 변환기, 진행 상태 helper와 wrapper를 함께 설치합니다. 식별 가능한 예전 ActivitySmith 지침 구간은 새 관리 구간으로 교체해 지침이 이중으로 남지 않게 합니다. 구간 밖 개인 지침, 기존 notifier 인수, Keychain 키와 MCP 인증은 보존합니다. 지침 구간이 모호하거나 관리 파일이 수정돼 있으면 검토를 위해 중단합니다.

Keychain에 정상 키가 있으면 키를 다시 등록할 필요가 없습니다. 예전 셸 설정에 `ACTIVITYSMITH_API_KEY`를 직접 내보내는 줄이 있다면 먼저 Keychain 키를 확인한 뒤 그 줄을 제거하고 새 터미널을 여세요. 이미 실행 중인 셸의 환경값은 재시작하거나 명시적으로 해제하기 전까지 유지됩니다.

Codex를 재시작한 뒤 `activitysmith-test`와 새 작업의 완료 알림을 확인하세요. 새로 감싼 명령부터 공통 진행 상태가 전달되며, 기존 세션에 소급 적용되지는 않습니다. Computer Use 재시작 처리는 아래에 설명돼 있습니다. 외부 callback 실행과 Watchsmith 설치 검증은 구분합니다.

되돌리려면 관련 작업을 멈추고 설치 시 출력된 ID로 `./install.sh --rollback TRANSACTION_ID --quiesced`를 실행합니다. 비공개 복구 기록은 Git에 넣지 마세요. [업데이트·복구 상세 안내](docs/UPGRADING.md)를 참고하세요.

## 최초 이전 이후의 업데이트

업데이트 기능을 포함한 버전을 설치하면 다음 명령이 함께 설치됩니다.

```bash
watchsmith version
watchsmith update --check
# 실행 중인 작업을 마치고 관련 앱을 닫은 뒤 적용:
watchsmith update --quiesced
watchsmith rollback --quiesced
```

공식 정식 릴리스를 확인하고 패키지를 검증한 뒤, 기존 설치기와 복구 기록을 사용합니다. 최초 이전 이후에는 Git이나 저장소 폴더가 없어도 업데이트할 수 있습니다. v0.1.0에는 이 명령이 없으므로 기능이 포함된 릴리스까지 한 번은 기존 방식으로 업그레이드해야 합니다. 업데이트 명령은 v0.2.0부터 제공합니다.

`--check`는 로컬 파일을 변경하지 않습니다. 적용에는 작업 종료를 확인하는 `--quiesced`가 필요하며 자동으로 프로세스를 멈추지는 않습니다. `rollback`은 가장 최근 설치 변경을 복원합니다. 체크섬은 손상 검사용이며 배포자 서명은 아닙니다. [업데이트·배포 상세 안내](docs/UPDATES.md)를 참고하세요. 설치 과정 간소화는 이후 별도로 진행합니다.

## 설치 프로그램이 하는 일

설치 후 구조는 대략 다음과 같습니다.

```text
~/.codex/
├── AGENTS.md
├── config.toml
├── bin/
│   ├── watchsmith
│   ├── watchsmith_setup.py
│   ├── watchsmith_update.py
│   ├── watchsmith_install.py
│   ├── watchsmith_config.py
│   ├── codex-watch
│   ├── watchsmith_result.py
│   ├── watchsmith_progress.py
│   ├── watchsmith_delivery.py
│   ├── activitysmith_notify.py
│   ├── watchsmith_notify_dispatcher.py
│   ├── activitysmith-keychain-setup
│   └── activitysmith-test
└── watchsmith/
    ├── previous_notify.json
    ├── installation.json
    ├── delivery.sqlite3
    └── transactions/
```

기존 `config.toml`에 top-level `notify`가 존재하면 installer가 argv를 `previous_notify.json`에 보존합니다.

Computer Use가 없는 경우 Codex의 notifier는 Watchsmith dispatcher로 연결됩니다. Computer Use가 있으면 아래 재시작 호환성 설명처럼 그 안쪽에 dispatcher를 연결합니다.

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

installer는 [`config/activitysmith-agents.md`](config/activitysmith-agents.md)의 표시된 구간을 `~/.codex/AGENTS.md`에 추가하거나 갱신합니다. 이전 파일을 백업하고 구간 밖의 지침은 유지합니다.

기본 판단 기준은 다음과 같습니다.

- 약 1분 이상 걸릴 가능성이 있으면 ActivitySmith 사용을 적극 고려
- 여러 단계 또는 여러 tool call이 필요한 작업이면 ActivitySmith 사용
- 처음에는 짧은 작업으로 판단했더라도 1분 이상 진행되면 ActivitySmith로 승격
- 의미 있는 진행 변화는 Live Activity
- 완료, 실패, blocker, 사용자 입력 필요 시 Push
- prompt 전문, credential, 고객 데이터, 소스코드 전문, 회사 기밀은 ActivitySmith로 보내지 않음

개인 설정은 다음 파일의 표시된 구간 밖에 작성하세요. 재설치하면 관리 구간 내부는 새 정책으로 교체됩니다.

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

지원하지 않으면 MCP stream이 이미 존재할 가능성이 없는 경우에만 Push 알림으로 fallback합니다.

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

## 기존 설치 업데이트 및 알림 조율

`./install.sh --check`로 변경 없이 기존 설치를 점검하세요. 진행 중인 Codex/watchdog 작업을 마치고 관련 앱을 닫은 뒤 `./install.sh --upgrade --quiesced`를 실행합니다. 기존 `CODEX_HOME`, Keychain 키, MCP 인증을 재사용합니다. 설치기는 비공개 복구 기록을 남기며, 알 수 없거나 수정된 관리 파일은 덮어쓰지 않습니다. 설치 후 Codex를 재시작하고 실제 수신을 확인하세요.

복구는 `./install.sh --rollback latest --quiesced`, 제거는 `./uninstall.sh --quiesced`입니다. 최초 보관한 상태에서 기존 notifier가 필요로 하는 파일을 복원합니다. 사용자가 notifier를 바꾼 경우 해당 설정과 의존할 수 있는 실행 파일을 함께 보존합니다. [업데이트·복구 상세 안내](docs/UPGRADING.md)를 참고하세요.

관리하는 완료 notifier는 로컬 전송 기록을 공유해 동일 이벤트의 중복 전송을 조율합니다. **상세 MCP 알림과 일반 hook이 같은 정확한 thread·turn ID를 확보한 경우에만** 상세 성공 기록으로 일반 알림을 생략할 수 있습니다. 현재 확인한 클라이언트에서 완료 전 turn ID 자동 연결은 인증되지 않았으며, ID가 없으면 기존 일반 알림을 유지합니다. wrapper 내부 진행 알림은 관리 지침을 통해 같은 stream 키를 공유합니다. wrapper 밖 Desktop 작업은 독립적이며, Computer Use 완료 callback 호환성은 아직 미해결입니다.

## 상세 작업 결과 공유 (선택 사항)

사용자가 동의하면 에이전트는 결과·수행 내용·검증 근거·남은 문제·다음 단계로 정리한 요약을 ActivitySmith MCP의 metadata로 보낼 수 있습니다. metadata도 ActivitySmith 서버에 저장되므로 원본 대화·소스코드·비밀 정보를 자동 복사하지 않습니다. 기본값은 일반 상태 알림입니다.

`watchsmith_result.py`는 로컬 결과를 검증하고 기존 MCP 도구에 넘길 인수만 출력합니다. 직접 전송하거나 파일을 업로드하지 않습니다. `--share-details`는 검토한 요약을 포함하고, `--include-result-link`는 이미 존재하며 공유가 허용된 HTTPS 결과 페이지를 선택적으로 연결합니다. 별도 서버는 필요하지 않습니다. [결과 형식 및 사용 절차](docs/RESULTS.md)와 [예시](config/result-example.json)를 참고하세요.

MCP 기록 조회로 metadata 저장을 확인했으며, 사용자가 iOS 앱에서 상세 항목·줄바꿈 표시를 확인했습니다. 결과 링크 접근은 아직 검증하지 않았습니다. 기존 완료 hook에서 별도 Push가 올 수 있으며, 상세·일반 알림의 조율에는 위에서 설명한 동일한 thread·turn 식별자가 필요합니다.

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
./uninstall.sh --quiesced
```

설치 이력에서 기존 notifier의 의존 파일을 먼저 복원한 뒤 설정을 되돌립니다. 사용자가 notifier를 바꿨다면 의존성 보호를 위해 실행 파일도 유지합니다.

`AGENTS.md`에 추가된 tagged block과 Keychain의 API Key는 사용자가 직접 검토할 수 있도록 자동 삭제하지 않습니다.

## License

MIT

## 설치 안전성 및 로컬 테스트

TOML 검증을 위해 Python 3.11 이상이 필요합니다. `CODEX_HOME`을 지원하며 기본값은 `~/.codex`입니다. 설치된 dispatcher는 자신의 위치를 기준으로 상태 파일과 notifier를 찾으므로 GUI 프로세스가 `CODEX_HOME`을 전달하지 않아도 동작합니다.

installer는 전체 TOML을 검증한 뒤 최상위 `notify`만 교체합니다. 여러 줄 배열과 따옴표로 감싼 키를 지원하며 중첩 설정은 유지합니다. 잘못된 TOML이나 문자열이 아닌 notify 인수가 있으면 설정을 수정하지 않고 중단합니다. 비공개 복구 기록에 원본을 보관하며 개별 설정 파일은 원자적으로 교체합니다. 동일한 dispatcher를 재설치하면 기존 notifier 기록을 보존합니다. 기존 notifier가 없었던 경우 JSON `null`을 저장합니다. 복원 정보가 없으면 추측해서 덮어쓰지 않고 재설치·제거를 중단합니다.

제거 시 최상위 notifier가 이 설치의 dispatcher인 경우에만 이전 인수 배열을 복원합니다. 사용자가 변경한 notifier는 유지합니다. notify의 표기 형식은 정규화될 수 있으며 원문은 백업에 남습니다. 재설치 시 관리하는 전역 정책 구간도 갱신합니다. 복구 기록을 이용한 설치 롤백을 제공합니다. 업데이트 안내를 참고하세요.

실제 Codex 설정을 변경하거나 알림을 보내지 않는 회귀 테스트:

```bash
python3 -m unittest discover -s tests -v
```

테스트는 설치·제거, 기록용 notifier로의 정확한 인수 전달, 모의 CLI를 이용한 일반 완료 명령 구성을 검증합니다. 실제 Computer Use 클라이언트, Codex 이벤트 발생, 모바일 수신을 검증한 것은 아닙니다.

## 진행 알림 경로 조율

`codex-watch`가 감싼 단일 실행에서는 관리 지침과 watchdog이 로컬 실행 상태 및 Live Activity 키를 공유합니다. MCP 성공 등록 후에는 fallback을 억제하고, watchdog이 먼저 시작했다면 MCP가 같은 키로 이어받습니다. 완료 hook의 turn별 조율은 별도로 유지합니다. Desktop 등 wrapper 밖의 작업은 자동 연결되지 않습니다. 적용하려면 실행 중인 작업을 종료한 뒤 `./install.sh --upgrade --quiesced`를 실행하고 Codex를 다시 시작하세요. [상세 동작과 한계](docs/PROGRESS.md)를 참고하세요.

## Computer Use 재시작 호환성

Computer Use를 사용하는 경우 설치기는 `Codex → Computer Use → Watchsmith dispatcher` 순서로 연결합니다. Watchsmith는 안쪽에 있던 기존 notifier와 자체 알림을 실행하므로 재시작 후 Computer Use가 이중으로 들어가지 않습니다.

이전 설치에서 재시작으로 바깥 연결이 추가된 경우, 설치 기록과 저장된 원본이 일치하는지 확인하고 중복된 이전 Computer Use 구간만 정리합니다. 식별할 수 없는 구성은 임의로 변경하지 않습니다. 정리 후 재설치는 변경 없이 끝나며, 제거 시 기존 notifier와 Computer Use를 보존합니다. 신규 사용자가 추가로 설정할 부분은 없습니다.

이전에 관찰한 외부 callback 시간 초과는 watchdog의 고장 근거가 아닙니다. 설치 점검은 연결 구성을 검증하며 외부 callback 자체의 정상 실행을 보증하지는 않습니다.

## 기여 및 버전 관리

기능별 브랜치, Conventional Commits, PR 통합, 검증과 버전 태그 규칙은
[CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.
