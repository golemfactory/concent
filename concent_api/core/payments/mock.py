
class MockedPayments():
    def sum_payments(list_of_payments):
        return sum([item.amount for item in list_of_payments])

    def get_client_eth_account():
        return True

    def get_number_of_eth_block(request):
        if 'HTTP_TEMPORARY_ETH_BLOCK' in request.META:
            return int(request.META['HTTP_TEMPORARY_ETH_BLOCK'])

    def payment_summary(request = None, subtask_results_accepted_list = None, list_of_transactions = None, list_of_forced_payments = None):
        if 'HTTP_TEMPORARY_V' in request.META:
            return int(request.META['HTTP_TEMPORARY_V'])

    def get_list_of_transactions(_T0 = None, current_time = None, _to_block = None, _payer_address = None, _payee_address = None, request = None):
        '''
        Function which return list of transactions from payment API
        where timestamp >= T0
        '''

        if 'HTTP_TEMPORARY_LIST_OF_TRANSACTIONS' in request.META:
            if bool(request.META['HTTP_TEMPORARY_LIST_OF_TRANSACTIONS']):
                return [{'timestamp': current_time - 3700}, {'timestamp': current_time - 3800}, {'timestamp': current_time - 3900}]
            else:
                return [{'timestamp': current_time - 22}, {'timestamp': current_time - 23}, {'timestamp': current_time - 24}]

    def get_forced_payments(_T0 = None, _requestor_address = None, _provider_address = None, _to_block = None, request = None, current_time = None):
        '''
        Function which return list of forced paysments from payment API
        where t0 <= payment_ts + PAYMENT_DUE_TIME + PAYMENT_GRACE_PERIOD
        '''

        if 'HTTP_TEMPORARY_LIST_OF_FORCED_TRANSACTIONS' in request.META:
            if bool(request.META['HTTP_TEMPORARY_LIST_OF_FORCED_TRANSACTIONS']):
                return [{'timestamp': current_time - 3700}, {'timestamp': current_time - 3800}, {'timestamp': current_time - 3900}]
            else:
                return [{'timestamp': current_time - 22}, {'timestamp': current_time - 23}, {'timestamp': current_time - 24}]

    def make_payment_to_provider(_V = None, _requestor_ethereum_public_key = None, _provider_ethereum_public_key = None):
        '''
        Concent makes transaction from requestor's deposit to provider's account on amount V.
        If there is less then V on requestor's deposit, Concent transfers as much as possible.
        '''
        return True
