## 프로젝트 개요

본 프로젝트는 AI4I Predictive Maintenance Dataset을 기반으로 수행되었다.
설비 센서 데이터를 활용하여 제조 운영 KPI를 직접 설계하였으며, 설비 상태 평가 및 제조 AI 분석 환경 구축을 목적으로 한다.
(\*) 표시가 포함된 컬럼은 원본 AI4I 데이터에 존재하지 않는 컬럼이며, 실제 제조 현장에서 활용되는 운영 지표를 참고하여 프로젝트 목적에 맞게 설계한 커스텀 컬럼이다.

# 1. 원본 데이터 컬럼

| 컬럼명                  | 설명                     | 단위 |
| ----------------------- | ------------------------ | ---- |
| UDI                     | 데이터 고유 번호         | -    |
| Product ID              | 제품 ID                  | -    |
| Type                    | 제품 타입 (L/M/H)        | -    |
| Air temperature [K]     | 외기 온도                | K    |
| Process temperature [K] | 공정 온도                | K    |
| Rotational speed [rpm]  | 회전 속도                | rpm  |
| Torque [Nm]             | 토크                     | Nm   |
| Tool wear [min]         | 공구 마모 시간           | min  |
| Machine failure         | 설비 고장 여부           | 0/1  |
| TWF                     | Tool Wear Failure        | 0/1  |
| HDF                     | Heat Dissipation Failure | 0/1  |
| PWF                     | Power Failure            | 0/1  |
| OSF                     | Overstrain Failure       | 0/1  |
| RNF                     | Random Failure           | 0/1  |

# 2. 프로젝트 생성 컬럼

| 컬럼명                   | 설명           | 단위                               |
| ------------------------ | -------------- | ---------------------------------- |
| (\*)Production_Qty       | 생산량         | EA                                 |
| (\*)Availability         | 설비 가동률    | %                                  |
| (\*)Quality_Rate         | 품질률         | %                                  |
| (\*)Defect_Rate          | 불량률         | %                                  |
| (\*)Power_Consumption    | 전력 사용량    | kWh                                |
| (\*)Performance          | 설비 성능 지표 | %                                  |
| (\*)OEE                  | 설비종합효율   | %                                  |
| (\*)Risk_Level           | 설비 위험도    | Low / Medium / Warning / High      |
| (\*)Maintenance_Priority | 정비 우선순위  | Normal / Plan / Urgent / Immediate |
| (\*)Equipment_ID         | 설비 식별 번호 | -                                  |
| (\*)Line                 | 생산 라인 정보 | -                                  |

# 3. 데이터 분류

## ① 센서 데이터

설비에 부착된 센서가 측정한 원본 데이터.

- Air temperature [K]
- Process temperature [K]
- Rotational speed [rpm]
- Torque [Nm]
- Tool wear [min]

## ② 고장 정보

설비의 고장 여부 및 고장 원인을 나타내는 데이터.

- Machine failure
- TWF
- HDF
- PWF
- OSF
- RNF

## ③ 제조 KPI

설비 운영 효율을 평가하기 위한 핵심 운영 지표.

- Production_Qty
- Availability
- Quality_Rate
- Defect_Rate
- Performance
- OEE

## ④ 운영 지표

설비 상태 판단 및 의사결정을 지원하는 지표.

- Risk_Level
- Maintenance_Priority

## ⑤ 운영 정보

설비 및 생산 라인을 식별하기 위한 정보.

- Equipment_ID
- Line

# 4. 핵심 KPI 설명

## (\*)Production_Qty

설비가 생산한 제품 수량.
생산량은 제조 생산성을 평가하는 대표적인 지표이다.

## (\*)Availability

설비가 정상적으로 운영되는 시간을 나타내는 지표.
높은 가동률은 설비 운영 효율이 우수함을 의미한다.

## (\*)Quality_Rate

생산된 제품 중 양품 비율을 나타내는 지표.

## (\*)Defect_Rate

생산된 제품 중 불량품 비율을 나타내는 지표.

## (\*)Performance

설비의 목표 성능 대비 실제 성능 수준을 나타내는 지표.

## (\*)OEE

Overall Equipment Effectiveness.

설비종합효율.
Availability, Performance, Quality를 종합하여 계산하는 제조 핵심 KPI이다.

```
OEE = Availability × Performance × Quality
```

제조 현장에서 가장 많이 활용되는 설비 운영 지표 중 하나이다.

## (\*)Risk_Level

설비 위험 수준을 나타내는 운영 지표.
| Risk Level | OEE 기준 | 의미 |
| ---------- | ----------------- | --------- |
| Low | 85 이상 | 매우 우수 |
| Medium | 70 이상 ~ 85 미만 | 양호 |
| Warning | 60 이상 ~ 70 미만 | 주의 |
| High | 60 미만 | 위험 |

## (\*)Maintenance_Priority

설비 점검 및 정비 우선순위를 나타내는 운영 지표.
| Priority | 의미 |
| --------- | -------------- |
| Normal | 정상 운영 |
| Plan | 정기 점검 권장 |
| Urgent | 우선 점검 필요 |
| Immediate | 즉시 점검 필요 |

# 5. 설비 상태 변화 과정

센서 데이터 변화

- Tool Wear 증가
- Torque 증가
- Process Temperature 증가

↓

설비 성능 저하

- Availability 감소
- Quality_Rate 감소
- Production_Qty 감소

↓

설비 효율 저하

- OEE 감소

↓

운영 리스크 증가

- Risk_Level 상승
- Maintenance_Priority 상승

# 6. 프로젝트 활용 방향

본 프로젝트에서는 센서 데이터와 제조 KPI를 종합 분석하여 다음과 같은 제조 AI 분석 환경을 구축한다.

- 설비 상태 분석
- OEE 분석
- 위험 설비 탐지
- 정비 우선순위 추천
- AI 기반 설비 상태 설명
- 제조 AI Copilot 구현
