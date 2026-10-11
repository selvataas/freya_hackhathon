# Freya Bank – Service contract for the phone agent

All services are called with an HTTP POST and a JSON body, under the base address of the bank's service.
Every answer is JSON with `ok` (true or false). When `ok` is false, `error` says why and nothing was done.

## verify_identity

`POST /verify_identity` — Check one security answer. Three wrong answers in total end the check.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `field` | string | yes | `date_of_birth`, `phone_last4` |  |
| `answer` | string | yes |  | For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits. |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |
| `verified` | boolean | no |  |  |
| `wrong_answers_left` | integer | no |  |  |
| `all_verified` | boolean | no |  |  |
| `hint` | string | no | `day_month_swapped` |  |

## get_account

`POST /get_account` — The late products. Refused until both questions are passed.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |
| `products` | list of objects with: product_id (string), type (string), card_last4 (string), past_due (number), days_late (integer), minimum_payment (number), instalment_amount (number) | no |  |  |

## create_promise

`POST /create_promise` — Record a payment promise. One per product.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `product_id` | string | yes |  |  |
| `amount` | number | yes |  |  |
| `date` | string | yes |  |  |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |
| `promise_id` | string | no |  |  |

## add_note

`POST /add_note` — Brief B: record why a product ended without a promise.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `product_id` | string | yes |  |  |
| `reason` | string | yes | `refused`, `hardship`, `dispute`, `paid`, `service_error` |  |
| `text` | string | no |  |  |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |

## schedule_callback

`POST /schedule_callback` — Book a callback.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `date` | string | yes |  |  |
| `time` | string | yes |  | HH:MM |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |

## transfer_to_agent

`POST /transfer_to_agent` — Hand the call to a person.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `queue` | string | yes | `restructuring`, `general`, `support` |  |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |

## close_call

`POST /close_call` — End the call. Always the last tool call. Nothing is accepted after it.

Request fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `customer_id` | string | yes |  |  |
| `outcome` | string | yes | `promise`, `paid`, `transferred`, `no_promise`, `not_verified`, `not_reached` |  |
| `reason` | string | no |  | Required for every outcome except promise and paid. See the table in the brief. |

Answer fields:

| Field | Type | Required | Allowed values | Meaning |
|---|---|---|---|---|
| `ok` | boolean | no |  |  |
| `error` | string | no |  |  |
