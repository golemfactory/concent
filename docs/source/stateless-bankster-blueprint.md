## Stateless Bankster

Bankster is an intermediate layer between Concent Core and the Ethereum Client (Geth).
All communication with the Ethereum Client is performed via Golem's Smart Contracts Interface (SCI) which is used as a library.

This specification describes a limited version of the mechanism that only takes into account deposit status listed on the blockchain.
It's not aware of parallel claims made by Concent against the same deposit and may decide that funds are available while they'll actually be gone when the use case finishes.
It's stateless - does not store existing claims in the database and check them when processing other claims.

A more complete version that tracks deposit claims is described in #479.

### Components and communication
![bankster-components](https://user-images.githubusercontent.com/137030/41231712-4e124bfa-6d84-11e8-8be2-3f085ff1d3dc.png)

### API

#### `POST bankster/claim-deposit/` endpoint
- **Input format**: JSON
- **Output format**: JSON

The purpose of this endpoint is to check whether the clients participating in a use case have enough funds in their deposits to cover all the costs associated with the use case in the pessimistic scenario.

Concent core communicates with this endpoint at the beginning of any use case that may require payment from deposit within a single subtask.
Currently those are `ForcedAcceptance` and `AdditionalVerification`.
`ForcedPayment` use case operates on more than one subtask and for that reason requires a separate endpoint.

The funds are checked in anticipation of a future payment but it does not necessarily mean that exactly that amount will be paid out or even that it will actually be paid.
The actual amount paid will depend on the outcome of the use case.

##### Input
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                | no       | ID of the subtask.
| `concent_use_case`              | `ConcentUseCase`      | no       | Use case in which Concent claims the deposit.
| `requestor_ethereum_public_key` | string                | no       | Address of the Ethereum account belonging to the requestor. Cannot be the same as `provider_ethereum_public_key`. Comes from `TaskToCompute`.
| `provider_ethereum_public_key`  | string                | no       | Address of the Ethereum account belonging to the provider. Cannot be the same as `requestor_ethereum_public_key`. Comes from `TaskToCompute`.
| `subtask_cost`                  | decimal               | no       | The cost of performing the work on the subtask that the requestor has agreed to pay the provider. Comes from `TaskToCompute.price` multiplied by maximum task duration. Must be greater than zero.

##### `ConcentUseCase` enum
- `ForcedAcceptance`
- `AdditionalVerification`
- `ForcedPayment`

##### Output
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `requestor_has_enough_deposit`  | bool                  | no       | `True` if requestor currently has enough funds in his deposit to pay.
| `provider_has_enough_deposit`   | bool                  | yes      | `True` if requestor currently has enough funds in his deposit to pay.

##### Sequence of operation
1. **Claim calculation**: Bankster determines the amount that needs to be claimed from each account:
    - In `ForcedAcceptance` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider does not pay anything.
    - In `AdditionalVerification` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider needs to pay verification cost (which is constant and determined by Concent's settings).
2. **Deposit query**:
    - Bankster asks SCI about the amount of funds available in requestor's deposit.
    - If the amount claimed from provider's deposit is non-zero, Bankster asks SCI about the amount of funds available in his deposit.
3. **Requestor's spare deposit check**:
    - **Claims against requestor's deposit can be paid partially** because the service has already been performed by the provider and giving him something is better than giving nothing.
        If the requestor's deposit is zero, we can't add a new claim.
        `requestor_has_enough_deposit` is `False`.
    - Otherwise `requestor_has_enough_deposit` is `True`.
4. **Provider's spare deposit check**: If the amount claimed from his deposit is non-zero.
    - **Claims against provider's deposit must be paid in full** because they're payments for using Concent and we did not perform the service yet so we can just refuse.
      If the provider's claim is greater than his current deposit, we can't add a new claim.
        - `provider_has_enough_deposit` is `False`.
    - Otherwise `provider_has_enough_deposit` is `True`.
5. **Response**: If everything goes well, Bankster sends a HTTP 200 response.
    - Bankster returns the values of `requestor_has_enough_deposit` and `provider_has_enough_deposit`.

#### `POST bankster/finalize-payments/` endpoint
- **Input format**: JSON
- **Output format**: JSON

This endpoint tells Bankster to pay out funds from deposit.

Concent core communicates with this endpoint at the end of any use case that may require payment from deposit within a single subtask.
Currently those are `ForcedAcceptance` and `AdditionalVerification`.
`ForcedPayment` use case operates on more than one subtask and for that reason requires a separate endpoint.

For each claim, Bankster uses SCI to submit an Ethereum transaction to the Ethereum client which then propagates it to the rest of the network.
Hopefully the transaction is included in one of the upcoming blocks on the blockchain.

If there's not enough funds at the moment, the amount to pay is decreased.
If there's nothing at all, the claim is discarded without payment.

##### Input
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                | no       | ID of the subtask.
| `concent_use_case`              | `ConcentUseCase`      | no       | Use case in which Concent claims the deposit.
| `requestor_ethereum_public_key` | string                | no       | Address of the Ethereum account belonging to the requestor. Cannot be the same as `provider_ethereum_public_key`. Comes from `TaskToCompute`.
| `provider_ethereum_public_key`  | string                | no       | Address of the Ethereum account belonging to the provider. Cannot be the same as `requestor_ethereum_public_key`. Comes from `TaskToCompute`.
| `subtask_cost`                  | decimal               | no       | The cost of performing the work on the subtask that the requestor has agreed to pay the provider. Comes from `TaskToCompute.price` multiplied by maximum task duration. Must be greater than zero.

##### Output
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `requestors_claim_payment_info` | `ClaimPaymentInfo`    | no       | Information about the payment made from requestor's deposit.
| `providers_claim_payment_info`  | `ClaimPaymentInfo`    | yes      | Information about the payment made from provider's deposit. Empty if and only if the claim against provider's deposit is zero.

###### ClaimPaymentInfo
| Parameter                     | Type                    | Optional | Remarks                                                                                                                 |
|-------------------------------|-------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `tx_hash`                     | string                  | yes      | Hash of the Ethereum transaction that has been created for the payment. Empty if and only if `amount_paid` is zero.
| `payment_ts`                  | timestamp               | yes      | Timestamp inserted into the transaction. Empty if and only if `tx_hash` is empty.
| `amount_paid`                 | decimal                 | no       | The amount that the transaction covers. Non-negative.
| `amount_pending`              | decimal                 | no       | The remaining amount that has not been paid. Non-negative.

##### Sequence of operation
1. **Claim calculation**: Bankster determines the amount that needs to be claimed from each account:
    - In `ForcedAcceptance` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider does not pay anything.
    - In `AdditionalVerification` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider needs to pay verification cost (which is constant and determined by Concent's settings).
2. **Deposit query**:
    - Bankster asks SCI about the amount of funds available in requestor's deposit.
    - If the amount claimed from provider's deposit is non-zero, Bankster asks SCI about the amount of funds available in his deposit.
3. **Payment calculation**: Bankster reduces the amount to be paid if there's not enough funds in the deposit (for both the requestor and the provider).
    - If the deposit is zero, the payment is reduced to zero.
    - Otherwise if the deposit does not have enough funds to cover the whole claim, the payment is reduced to the size of the deposit.
4. **Transaction**: for both the requestor and the provider:
    - If claim is zero, the corresponding `claim_payment_info` is empty.
    - Otherwise if claim is non-zero but the deposit is empty, Bankster creates `ClaimPaymentInfo`
        - `tx_hash`: empty
        - `payment_ts`: empty
        - `amount_paid`: 0
        - `amount_pending`: the full amount claimed
    - Otherwise:
        - Bankster uses SCI to create an Ethereum transaction.
        - Bankster creates `ClaimPaymentInfo`
            - `tx_hash`: hash of the transaction
            - `payment_ts`: `payment_ts` value from the transaction
            - `amount_paid`: the amount to be paid
            - `amount_pending`: full amount claimed minus the amount paid
5. **Response**: Bankster returns the created `ClaimPaymentInfo` objects.

#### `POST bankster/settle-overdue-acceptances/` endpoint
- **Input format**: JSON
- **Output format**: JSON

The purpose of this endpoint is to calculate the total amount that the requestor owes provider for completed computations and transfer that amount from requestor's deposit.
Concent Core is responsible for validating provider's claims and Bankster only calculates and executes the payment.

The provider proves to Concent that the computations were performed and accepted and Concent Core asks Bankster to compare the total value with the amount actually paid by the requestor, either directly or from deposit.
If it turns out that the total value of provider's claims was not covered completely, Concent transfers the missing amount from requestor's deposit.
If the deposit is not large enough to cover the whole amount, Concent transfers as much as possible.
After this operation the provider can no longer claim any other overdue payments that happened before the deposit transfer.

##### Input
| Parameter                       | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `requestor_ethereum_public_key` | string                      | no       | Address of the Ethereum account belonging to the requestor. Cannot be the same as `provider_ethereum_public_key`. Comes from `TaskToCompute`.
| `provider_ethereum_public_key`  | string                      | no       | Address of the Ethereum account belonging to the provider. Cannot be the same as `requestor_ethereum_public_key`. Comes from `TaskToCompute`.
| `acceptances`                   | list of `SubtaskAcceptance` | no       | List of dicts describing each acceptance. The list must contain at least one object.

###### `SubtaskAcceptance`
| Field                           | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                      | no       | ID of the subtask.
| `payment_ts`                    | timestamp                   | no       | `payment_ts` timestamp from the acceptance message.
| `amount`                        | decimal                     | no       | Amount to be paid.

##### Output
| Parameter                       | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `requestors_claim_payment_info` | `ClaimPaymentInfo`          | yes      | Information about the payment made from requestors's deposit. Empty if and only if the claim against requestors's deposit is zero.

##### Sequence of operation
1. **Deposit query**:
    - Bankster asks SCI about the amount of funds available in requestor's deposit.
2. **Claim calculation**:
    - Bankster sums up the amount specified in acceptances.
    - Bankster asks SCI for the list of all relevant payments listed on the blockchain (both normal payments performed by the requestor and forced payments performed by Concent).
    - Bankster computes the amount that is still owed to the provider.
    - Bankster compares the amount with the available deposit.
        - If the whole amount can't be paid, Concent lowers it to pay as much as possible.
3. **Payment calculation**: Bankster reduces the amount to be paid if there's not enough funds in the deposit.
    - If the deposit is zero, the payment is reduced to zero.
    - Otherwise if the deposit does not have enough funds to cover the whole claim, the payment is reduced to the size of the deposit.
4. **Transaction**:
    - If claim is zero, `requestors_claim_payment_info` is empty.
    - Otherwise if claim is non-zero but the deposit is empty, Bankster creates `ClaimPaymentInfo`
        - `tx_hash`: empty
        - `payment_ts`: empty
        - `amount_paid`: 0
        - `amount_pending`: the full amount claimed
    - Otherwise:
        - Bankster uses SCI to create an Ethereum transaction.
        - Bankster creates `ClaimPaymentInfo`
            - `tx_hash`: hash of the transaction
            - `payment_ts`: `payment_ts` value from the transaction
            - `amount_paid`: the amount to be paid
            - `amount_pending`: full amount claimed minus the amount paid
5. **Response**: Bankster returns the created `ClaimPaymentInfo` object.
