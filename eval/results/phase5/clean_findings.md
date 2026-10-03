# Quality checks on clean translations

Every warning/error raised on finished translations of the public test documents, for manual review.

## Calibration set (Phase 2 + 3)


### hy-mt2-7b/rich_en_en-ja_vote (15 paragraphs): 1 finding(s)

- [warning] picture_text: slide 2: picture contains text (not translated)

### hy-mt2-7b/rich_ja_ja-en_vote (15 paragraphs): 1 finding(s)

- [warning] picture_text: slide 2: picture contains text (not translated)

### hy-mt2-7b/sample_en_en-ja_vote (63 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_ja_ja-en_vote (59 paragraphs): 0 finding(s)


### hy-mt2-7b/slides_en_en-ja_vote (61 paragraphs): 0 finding(s)


### hy-mt2-7b/spec_en_en-ja_vote (29 paragraphs): 0 finding(s)


### hy-mt2-7b/spec_en_scanned_en-ja_vote (29 paragraphs): 0 finding(s)


### hy-mt2-7b/spec_ja_ja-en_vote (29 paragraphs): 0 finding(s)


### hy-mt2-7b/spec_ja_scanned_ja-en_vote (29 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_en_en-ja_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_en_en-ko_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_en_en-my_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_en_en-th_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_en_en-zh_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/consistency_ja_ja-en_vote (32 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_en_en-ja_vote (63 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_en_en-ko_vote (63 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_en_en-my_vote (61 paragraphs): 9 finding(s)

- [warning] partly_translated: Left untranslated: firmware
  - source: Model FX-PCG2611-0 controller, firmware v3.2.1
  - translation: FX-PCG2611-0 မော်ဒယ် ထိန်းချုပ်ကိရိယာ၊ firmware v3.2.1
- [warning] partly_translated: Left untranslated: device
  - source: Edge device
  - translation: Edge device => အနားသတ် ကိရိယာ
- [warning] partly_translated: Left untranslated: platform
  - source: Cloud platform
  - translation: Cloud platform => ကလောက်ဒ် ပလက်ဖောင်း
- [warning] partly_translated: Left untranslated: port
  - source: Field controllers communicate over BACnet/IP and Modbus TCP; the gateway publishes telemetry to the cloud platform via MQTT over TLS (port 8
  - translation: လယ်ကွင်းထိန်းချုပ်ကိရိယာများသည် BACnet/IP နှင့် Modbus TCP တို့မှတစ်ဆင့် အချင်းချင်း ဆက်သွယ်ကြပါသည်။ ဂိတ်ဝ ကိရိယာသည် TLS (port 8883) မှတစ်ဆင
- [warning] partly_translated: Left untranslated: cloud, telemetry
  - source: IoT telemetry to cloud
  - translation: cloud သို့ IoT telemetry
- [warning] partly_translated: Left untranslated: pair
  - source: Twisted pair / IP
  - translation: Twisted pair => ကြိုးနှစ်ခွ  
IP => IP
- [warning] added_text: Has extra lines: the model may have added text
  - source: Twisted pair / IP
  - translation: Twisted pair => ကြိုးနှစ်ခွ  
IP => IP
- [warning] partly_translated: Left untranslated: dashboard
  - source: Web dashboard: https://bms.example.com/dashboard
  - translation: Web dashboard: https://bms.example.com/dashboard => ဝဘ် dashboard: https://bms.example.com/dashboard
- [warning] partly_translated: Left untranslated: edge, devices
  - source: Phase 2 (Q4 2026): IoT sensors and edge devices
  - translation: အဆင့် ၂ (၂၀၂၆ ခုနှစ်၊ စတုတ္ထသုံးလပတ်) – IoT အာရုံခံကိရိယာများနှင့် edge devices

### hy-mt2-7b/sample_en_en-th_vote (63 paragraphs): 1 finding(s)

- [warning] possible_omission: Shorter than expected: part of the text may be missing
  - source: Air Handling Unit (AHU) and Fan Coil Unit (FCU) control
  - translation: การควบคุม (AHU) และ (FCU)

### hy-mt2-7b/sample_en_en-zh_vote (63 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_ja_ja-en_vote (59 paragraphs): 0 finding(s)


## Held-out set (Phase 1, three models)


### hy-mt2-7b/sample_en_en-ja_verify (63 paragraphs): 2 finding(s)

- [warning] possible_omission: Shorter than expected: part of the text may be missing
  - source: Energy Management System (EMS) for energy consumption analysis
  - translation: エネルギー消費量分析用（EMS）
- [warning] glossary_term: Glossary: “energy management system” should be “エネルギー管理システム”
  - source: Energy Management System (EMS) for energy consumption analysis
  - translation: エネルギー消費量分析用（EMS）

### hy-mt2-7b/sample_en_en-ko_verify (63 paragraphs): 0 finding(s)


### hy-mt2-7b/sample_en_en-my_verify (61 paragraphs): 10 finding(s)

- [warning] possible_omission: Shorter than expected: part of the text may be missing
  - source: Energy Management System (EMS) for energy consumption analysis
  - translation: စွမ်းအင် သုံးစွဲမှုကို ခွဲခြမ်းစိတ်ဖြာရန်အတွက် (EMS)
- [warning] partly_translated: Left untranslated: firmware
  - source: Model FX-PCG2611-0 controller, firmware v3.2.1
  - translation: FX-PCG2611-0 မော်ဒယ် ထိန်းချုပ်ကိရိယာ၊ firmware v3.2.1
- [warning] partly_translated: Left untranslated: device
  - source: Edge device
  - translation: Edge device => အနားသတ် ကိရိယာ
- [warning] partly_translated: Left untranslated: platform
  - source: Cloud platform
  - translation: Cloud platform => ကလောက်ဒ် ပလက်ဖောင်း
- [warning] partly_translated: Left untranslated: port
  - source: Field controllers communicate over BACnet/IP and Modbus TCP; the gateway publishes telemetry to the cloud platform via MQTT over TLS (port 8
  - translation: လယ်ကွင်းထိန်းချုပ်ကိရိယာများသည် BACnet/IP နှင့် Modbus TCP တို့မှတစ်ဆင့် အချင်းချင်း ဆက်သွယ်ကြပါသည်။ ဂိတ်ဝ ကိရိယာသည် TLS (port 8883) မှတစ်ဆင
- [warning] partly_translated: Left untranslated: cloud, telemetry
  - source: IoT telemetry to cloud
  - translation: cloud သို့ IoT telemetry
- [warning] partly_translated: Left untranslated: pair
  - source: Twisted pair / IP
  - translation: Twisted pair => ကြိုးနှစ်ခွ  
IP => IP
- [warning] added_text: Has extra lines: the model may have added text
  - source: Twisted pair / IP
  - translation: Twisted pair => ကြိုးနှစ်ခွ  
IP => IP
- [warning] partly_translated: Left untranslated: dashboard
  - source: Web dashboard: https://bms.example.com/dashboard
  - translation: Web dashboard: https://bms.example.com/dashboard => ဝဘ် dashboard: https://bms.example.com/dashboard
- [warning] partly_translated: Left untranslated: edge, devices
  - source: Phase 2 (Q4 2026): IoT sensors and edge devices
  - translation: အဆင့် ၂ (၂၀၂၆ ခုနှစ်၊ စတုတ္ထသုံးလပတ်) – IoT အာရုံခံကိရိယာများနှင့် edge devices

### hy-mt2-7b/sample_en_en-th_verify (63 paragraphs): 2 finding(s)

- [warning] possible_omission: Shorter than expected: part of the text may be missing
  - source: Air Handling Unit (AHU) and Fan Coil Unit (FCU) control
  - translation: การควบคุม (AHU) และ (FCU)
- [warning] foreign_script: Contains characters from another language
  - source: Setpoint adjustment: cooling setpoint raised from 24 °C to 26 °C during peak hours
  - translation: การปรับค่าตั้ง点: ค่าตั้ง点สำหรับระบายความร้อนได้รับการเพิ่มขึ้นจาก 24 °C เป็น 26 °C ในช่วงเวลาที่มีความต้องการไฟฟ้าสูงสุด

### hy-mt2-7b/sample_en_en-zh_verify (63 paragraphs): 1 finding(s)

- [warning] number_changed: Number or unit missing or changed: 24
  - source: Alarm and equipment status monitoring 24/7
  - translation: 全天候监控报警状态以及设备状态。

### hy-mt2-7b/sample_ja_ja-en_verify (59 paragraphs): 0 finding(s)


### qwen3-8b/sample_en_en-ja_verify (63 paragraphs): 0 finding(s)


### qwen3-8b/sample_en_en-ko_verify (63 paragraphs): 0 finding(s)


### qwen3-8b/sample_en_en-my_verify (58 paragraphs): 1 finding(s)

- [warning] possible_omission: Shorter than expected: part of the text may be missing
  - source: Scheduled maintenance of the AHU filters is performed every 3 months.
  - translation: AHU ပိုးများကို ၃လတာ တစ်ကြိမ် စီ စောင့်ကြည့်ထားသည်။

### qwen3-8b/sample_en_en-th_verify (63 paragraphs): 0 finding(s)


### qwen3-8b/sample_en_en-zh_verify (63 paragraphs): 1 finding(s)

- [warning] token_missing: Identifier missing: AI
  - source: Phase 3 (2027): AI-based fault detection and diagnostics (FDD)
  - translation: 第三阶段（2027年）：基于人工智能的故障检测与诊断（FDD）

### qwen3-8b/sample_ja_ja-en_verify (59 paragraphs): 0 finding(s)


### cat-translate-7b/sample_en_en-ja_verify (63 paragraphs): 17 finding(s)

- [warning] partly_translated: Left untranslated: comparison
  - source: Protocol Comparison
  - translation: プロトコル比較

assistantcommentary
The user has requested a translation of the English term "Protocol Comparison" into Japanese. The translation s
- [warning] added_text: Has extra lines: the model may have added text
  - source: Protocol Comparison
  - translation: プロトコル比較

assistantcommentary
The user has requested a translation of the English term "Protocol Comparison" into Japanese. The translation s
- [warning] added_text: Has extra lines: the model may have added text
  - source: Protocol
  - translation: アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント

- [warning] added_text: Has extra lines: the model may have added text
  - source: Transport
  - translation: アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント

- [warning] added_text: Has extra lines: the model may have added text
  - source: Typical use
  - translation: アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント
アシスタント

- [warning] added_text: Has extra lines: the model may have added text
  - source: Network and Access
  - translation: ネットワークとアクセス

assistant
ネットワークとアクセス
- [warning] glossary_term: Glossary: “equipment status” should be “機器状態”
  - source: Alarm and equipment status monitoring 24/7
  - translation: アラーム と 機器ステータス の 24 時間 365 日監視
- [warning] glossary_term: Glossary: “alarm” should be “警報”
  - source: Alarm and equipment status monitoring 24/7
  - translation: アラーム と 機器ステータス の 24 時間 365 日監視
  - source: The building management system collects data from more than 2,000 points and sends alarms to the operator within 5 seconds.
  - translation: 建物管理システムは2,000点以上のデータを収集し、5秒以内にオペレーターにアラームを送信します。
- [warning] glossary_term: Glossary: “energy consumption” should be “エネルギー消費量”
  - source: Energy Management System (EMS) for energy consumption analysis
  - translation: エネルギー消費分析のためのエネルギー管理システム（EMS）
- [warning] glossary_term: Glossary: “building management system” should be “ビル管理システム”
  - source: The building management system collects data from more than 2,000 points and sends alarms to the operator within 5 seconds.
  - translation: 建物管理システムは2,000点以上のデータを収集し、5秒以内にオペレーターにアラームを送信します。
- [warning] glossary_term: Glossary: “occupancy sensor” should be “在室センサー”
  - source: Occupancy sensor
  - translation: 占有センサー
- [warning] glossary_term: Glossary: “web dashboard” should be “Webダッシュボード”
  - source: Web dashboard: https://bms.example.com/dashboard
  - translation: ウェブダッシュボード: https://bmsc.example.com/dashboard
- [error] token_changed: Identifier changed: HVAC → HVAAC
  - source: The Building Management System monitors and controls HVAC equipment.
  - translation: ビル管理システムは、HVAAC機器を監視・制御します。
- [error] token_changed: Identifier changed: HVAC → HVAAC
  - source: HVAC controllers
  - translation: HVAACコントローラー
- [error] token_changed: Identifier changed: BMS → BM
  - source: BMS server: 192.168.1.100 (VLAN 20)
  - translation: BMサーバー：192.168.1.100（VLAN 20）
- [error] token_changed: Identifier changed: https://bms.example.com/dashboard → https://bmsc.example.com/dashboard
  - source: Web dashboard: https://bms.example.com/dashboard
  - translation: ウェブダッシュボード: https://bmsc.example.com/dashboard
- [warning] token_added: Not in the original: https://bmsc.example.com/dashboard
  - source: Web dashboard: https://bms.example.com/dashboard
  - translation: ウェブダッシュボード: https://bmsc.example.com/dashboard

### cat-translate-7b/sample_ja_ja-en_verify (59 paragraphs): 11 finding(s)

- [warning] added_text: Has extra lines: the model may have added text
  - source: スマートビルディングプラットフォーム概要
  - translation: Smart Building Platform Overview

The Smart Building Platform is a comprehensive solution that integrates various technologies and services 
- [warning] added_text: Has extra lines: the model may have added text
  - source: 在室センサー
  - translation: Occupancy sensor
occupancy sensor
occupancy sensor
occupancy sensor
occupancy sensor
occupancy sensor
occupancy sensor
occupancy sensor
occu
- [warning] added_text: Has extra lines: the model may have added text
  - source: システム構成
  - translation: System Configuration

System Configuration

System Configuration

System Configuration

System Configuration

System Configuration

System C
- [warning] added_text: Has extra lines: the model may have added text
  - source: プロトコル比較
  - translation: Protocol Comparison

Protocol comparison is a process of comparing different protocols to determine their relative merits and drawbacks. Thi
- [warning] added_text: Has extra lines: the model may have added text
  - source: プロトコル
  - translation: Assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant

- [warning] added_text: Has extra lines: the model may have added text
  - source: 主な用途
  - translation: Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses
Main Uses

- [warning] added_text: Has extra lines: the model may have added text
  - source: デフォルトポート
  - translation: Assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant
assistant

- [warning] added_text: Has extra lines: the model may have added text
  - source: Webダッシュボード：https://bms.example.com/dashboard
  - translation: Web Dashboard: https://bmsc.example.com/dashboard
assistant
- [error] token_changed: Identifier changed: BMS → BM
  - source: BMSサーバー：192.168.1.100（VLAN 20）
  - translation: BM Server: 192.168.1.100 (VLAN 20)
- [error] token_changed: Identifier changed: https://bms.example.com/dashboard → https://bmsc.example.com/dashboard
  - source: Webダッシュボード：https://bms.example.com/dashboard
  - translation: Web Dashboard: https://bmsc.example.com/dashboard
assistant
- [warning] token_added: Not in the original: https://bmsc.example.com/dashboard
  - source: Webダッシュボード：https://bms.example.com/dashboard
  - translation: Web Dashboard: https://bmsc.example.com/dashboard
assistant
