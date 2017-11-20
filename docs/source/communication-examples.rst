Communication examples
######################


Constant values
+++++++++++++++

- `CONCENT_MESSAGING_TIME` = 1 hour


Scenarios
+++++++++

Provider forces computed task report via Concent
================================================

**Conditions**:

- Request from the provider.
- No `MessageForceReportComputedTask` with specified `task_id` was submitted yet.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/send/                      \
        --header "Content-Type: application/json"                        \
        --header "Accept:       application/json"                        \
        --data '{                                                        \
            "type":                    "MessageForceReportComputedTask", \
            "timestamp":               "2017-11-11T14:55:00Z",           \
            "message_task_to_compute": {                                 \
                "type":      "MessageTaskToCompute",                     \
                "timestamp": "2017-11-11T12:00:00Z",                     \
                "task_id":   133,                                        \
                "deadline":  "2017-11-11T15:00:00Z"                      \
            }                                                            \
        }'

**Response example**:

:Status:

    `202 ACCEPTED`


Concent rejects computed task immediately when deadline is exceeded
===================================================================

**Conditions**:

- Request from the provider.
- `MessageForceReportComputedTask` was submitted and provider has not received a response yet.
- Current time > `message_task_to_compute.deadline`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                    "MessageRejectReportComputedTask",
            "timestamp":               "2017-11-11T15:05:00Z",
            "reason":                  "deadline-exceeded",
            "message_task_to_compute": {
                "type":      "MessageTaskToCompute",
                "timestamp": "2017-11-11T12:00:00Z",
                "task_id":   133,
                "deadline":  "2017-11-11T15:00:00Z"
            }
        }


Concent forces computed task report on the requestor
====================================================

**Conditions**:

- Request from the requestor.
- `MessageForceReportComputedTask` was submitted.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- Current time <= `message_task_to_compute.deadline` + `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                    "MessageForceReportComputedTask",
            "timestamp":               "2017-11-11T14:55:00Z",
            "message_task_to_compute": {
                "type":      "MessageTaskToCompute",
                "timestamp": "2017-11-11T12:00:00Z",
                "task_id":   133,
                "deadline":  "2017-11-11T15:00:00Z"
            }
        }


Requestor accepts computed task via Concent
===========================================

**Conditions**:

- Request from the requestor.
- `MessageForceReportComputedTask` was submitted.
- Requestor has not submitted `MessageRejectReportComputedTask` or `MessageAckReportComputedTask` for this task yet.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- Current time <= `message_task_to_compute.deadline` + `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/send/                      \
        --header "Content-Type: application/json"                        \
        --header "Accept:       application/json"                        \
        --data '{                                                        \
            "type":                    "MessageAckReportComputedTask",   \
            "timestamp":               "2017-11-11T15:30:00Z",           \
            "message_task_to_compute": {                                 \
                "type":      "MessageTaskToCompute",                     \
                "timestamp": "2017-11-11T12:00:00Z",                     \
                "task_id":   133,                                        \
                "deadline":  "2017-11-11T15:00:00Z"                      \
            }                                                            \
        }'

**Response example**:

:Status:

    `202 ACCEPTED`


Requestor rejects computed task due to `MessageCannotComputeTask` or `MessageTaskFailure`
=========================================================================================

**Conditions**:

- Request from the requestor.
- `MessageForceReportComputedTask` was submitted.
- Requestor has not submitted `MessageRejectReportComputedTask` or `MessageAckReportComputedTask` for this task yet.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- Current time <= `message_task_to_compute.deadline` + `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/send/                           \
        --header "Content-Type: application/json"                             \
        --header "Accept:       application/json"                             \
        --data '{                                                             \
            "type":                        "MessageRejectReportComputedTask", \
            "timestamp":                   "2017-11-11T15:30:00Z",            \
            "reason":                      "cannot-compute-task",             \
            "message_cannot_compute_task": {                                  \
                "type":      "MessageCannotComputeTask",                      \
                "timestamp": "2017-11-11T11:00:00Z",                          \
                "reason":    "provider-quit",                                 \
                "task_id":   133                                              \
            }                                                                 \
        }'

**Response example**:

:Status:

    `202 ACCEPTED`


Concent passes computed task acceptance or rejection to the provider
====================================================================

**Conditions**:

- Request from the provider.
- Requestor has submitted `MessageRejectReportComputedTask` or `MessageAckReportComputedTask` for this task.
- If it's a rejection, it's not due to an exceeded deadline.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- Current time <= `message_task_to_compute.deadline` + 2 * `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                        "MessageRejectReportComputedTask",
            "timestamp":                   "2017-11-11T15:30:00Z",
            "reason":                      "cannot-compute-task",
            "message_cannot_compute_task": {
                "type":      "MessageCannotComputeTask",
                "timestamp": "2017-11-11T11:00:00Z",
                "reason":    "provider-quit",
                "task_id":   133
            }
        }


Concent overrides computed task rejection and sends acceptance message to the provider
======================================================================================

**Conditions**:

- Request from the provider.
- Requestor has submitted `MessageRejectReportComputedTask` for this task.
- The rejection is due to an exceeded deadline.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- Current time <= `message_task_to_compute.deadline` + 2 * `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                    "MessageAckReportComputedTask",
            "timestamp":               "2017-11-11T16:30:00Z",
            "message_task_to_compute": {
                "type":      "MessageTaskToCompute",
                "timestamp": "2017-11-11T12:00:00Z",
                "task_id":   133,
                "deadline":  "2017-11-11T15:00:00Z"
            }
        }


Concent accepts computed task due to lack of response from the requestor
========================================================================

**Conditions**:

- Request from the provider.
- Requestor has not submitted `MessageRejectReportComputedTask` or `MessageAckReportComputedTask` for this task.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- `message_task_to_compute.deadline` + `CONCENT_MESSAGING_TIME` <= current time <= `message_task_to_compute.deadline` + 2 * `CONCENT_MESSAGING_TIME`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                    "MessageAckReportComputedTask",
            "timestamp":               "2017-11-11T16:00:00Z",
            "message_task_to_compute": {
                "type":      "MessageTaskToCompute",
                "timestamp": "2017-11-11T12:00:00Z",
                "task_id":   133,
                "deadline":  "2017-11-11T15:00:00Z"
            }
        }


Requestor receives computed task report verdict out of band due to an overridden decision
=========================================================================================

**Conditions**:

- Request from the requestor.
- Requestor has submitted `MessageRejectReportComputedTask`.
- The rejection was due to an exceeded deadline.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive-out-of-band/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                               "MessageVerdictReportComputedTask",
            "timestamp":                          "2017-11-11T16:30:00Z",
            "message_force_report_computed_task": {
                "type":                    "MessageForceReportComputedTask",
                "timestamp":               "2017-11-11T14:55:00Z",
                "message_task_to_compute": {
                    "type":      "MessageTaskToCompute",
                    "timestamp": "2017-11-11T12:00:00Z",
                    "task_id":   133,
                    "deadline":  "2017-11-11T15:00:00Z"
                }
            },
            "message_ack_report_computed_task": {
                "type":                    "MessageAckReportComputedTask",
                "timestamp":               "2017-11-11T16:30:00Z",
                "message_task_to_compute": {
                    "type":      "MessageTaskToCompute",
                    "timestamp": "2017-11-11T12:00:00Z",
                    "task_id":   133,
                    "deadline":  "2017-11-11T15:00:00Z"
                }
            }
        }


Requestor receives task computation report verdict out of band due to lack of response
======================================================================================

**Conditions**:

- Request from the requestor.
- Requestor has not submitted `MessageRejectReportComputedTask` or `MessageAckReportComputedTask` for this task.
- `MessageForceReportComputedTask.timestamp` <= `message_task_to_compute.deadline`.
- `message_task_to_compute.deadline` + `CONCENT_MESSAGING_TIME` <= current time

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive-out-of-band/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `200 OK`

:Headers:

    .. code-block:: text

        Content-Type:                              application/json
        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0

:Body:

    .. code-block:: json

        {
            "type":                               "MessageVerdictReportComputedTask",
            "timestamp":                          "2017-11-11T16:30:00Z",
            "message_force_report_computed_task": {
                "type":                    "MessageForceReportComputedTask",
                "timestamp":               "2017-11-11T14:55:00Z",
                "message_task_to_compute": {
                    "type":      "MessageTaskToCompute",
                    "timestamp": "2017-11-11T12:00:00Z",
                    "task_id":   133,
                    "deadline":  "2017-11-11T15:00:00Z"
                }
            },
            "message_ack_report_computed_task": {
                "type":                    "MessageAckReportComputedTask",
                "timestamp":               "2017-11-11T16:30:00Z",
                "message_task_to_compute": {
                    "type":      "MessageTaskToCompute",
                    "timestamp": "2017-11-11T12:00:00Z",
                    "task_id":   133,
                    "deadline":  "2017-11-11T15:00:00Z"
                }
            }
        }


No response for the provider yet
================================

**Conditions**:

- `MessageForceReportComputedTask` was submitted.
- Current time <= `deadline` + `CONCENT_MESSAGING_TIME`
- No response is queued

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `204 NO CONTENT`

:Headers:

    .. code-block:: text

        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0


No out-of-band response for the provider yet
============================================

**Conditions**:

- `MessageForceReportComputedTask` was submitted.
- Current time <= `deadline` + `CONCENT_MESSAGING_TIME`
- No out-of-band response is queued

**Request example**:

.. code-block:: bash

    curl -X POST http://concent.golem.network/receive-out-of-band/ \
        --header "Accept: application/json"

**Response example**:

:Status:

    `204 NO CONTENT`

:Headers:

    .. code-block:: text

        Concent-Pending-Message-Count:             0
        Concent-Pending-Out-Of-Band-Message-Count: 0
