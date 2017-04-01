# -*- coding: utf-8 -*-

# Copyright(C) 2012 Romain Bignon
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.

from collections import OrderedDict
from functools import wraps
import urllib

from weboob.exceptions import BrowserIncorrectPassword, BrowserUnavailable
from weboob.browser.exceptions import HTTPNotFound
from weboob.browser import LoginBrowser, URL, need_login
from weboob.capabilities.bank import Account
from weboob.capabilities.base import NotAvailable

from .pages import (
    LoggedOut,
    LoginPage, IndexPage, AccountsPage, AccountsFullPage, CardsPage, TransactionsPage,
    UnavailablePage, RedirectPage, HomePage, Login2Page, ErrorPage,
    LineboursePage, InvestmentLineboursePage, MessagePage,
    IbanPage, AdvisorPage,
    NatixisPage, EtnaPage, NatixisInvestPage, NatixisHistoryPage, NatixisErrorPage,
    NatixisDetailsPage,
)


__all__ = ['BanquePopulaire']


class BrokenPageError(Exception):
    pass


def retry(exc_check, tries=4):
    """Decorate a function to retry several times in case of exception.

    The decorated function is called at max 4 times. It is retried only when it
    raises an exception of the type `exc_check`.
    If the function call succeeds and returns an iterator, a wrapper to the
    iterator is returned. If iterating on the result raises an exception of type
    `exc_check`, the iterator is recreated by re-calling the function, but the
    values already yielded will not be re-yielded.
    For consistency, the function MUST always return values in the same order.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(browser, *args, **kwargs):
            cb = lambda: func(browser, *args, **kwargs)

            for i in xrange(tries, 0, -1):
                try:
                    ret = cb()
                except exc_check as exc:
                    browser.logger.debug('%s raised, retrying', exc)
                    continue

                if not hasattr(ret, '__iter__'):
                    return ret  # simple value, no need to retry on items
                return iter_retry(cb, value=ret, remaining=i, exc_check=exc_check, logger=browser.logger)

            raise BrowserUnavailable('Site did not reply successfully after multiple tries')

        return wrapper
    return decorator


def no_need_login(func):
    # indicate a login is in progress, so LoggedOut should not be raised
    def wrapper(browser, *args, **kwargs):
        browser.no_login += 1
        try:
            return func(browser, *args, **kwargs)
        finally:
            browser.no_login -= 1

    return wrapper



class BanquePopulaire(LoginBrowser):
    login_page = URL(r'https://[^/]+/auth/UI/Login.*', LoginPage)
    index_page = URL(r'https://[^/]+/cyber/internet/Login.do', IndexPage)
    accounts_page = URL(r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=mesComptes.*',
                        r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=maSyntheseGratuite.*',
                        r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=accueilSynthese.*',
                        r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=equipementComplet.*',
                        r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=VUE_COMPLETE.*',
                        AccountsPage)

    iban_page = URL(r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=cyberIBAN.*',
                    r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=DETAIL_IBAN_RIB.*',
                    IbanPage)

    accounts_full_page = URL(r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=EQUIPEMENT_COMPLET.*',
                             AccountsFullPage)

    cards_page = URL(r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=ENCOURS_COMPTE.*', CardsPage)

    transactions_page = URL(r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=SELECTION_ENCOURS_CARTE.*',
                            r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=SOLDE.*',
                            r'https://[^/]+/cyber/internet/ContinueTask.do\?.*dialogActionPerformed=CONTRAT.*',
                            r'https://[^/]+/cyber/internet/Page.do\?.*',
                            r'https://[^/]+/cyber/internet/Sort.do\?.*',
                            TransactionsPage)

    error_page = URL(r'https://[^/]+/cyber/internet/ContinueTask.do', ErrorPage)
    unavailable_page = URL(r'https://[^/]+/s3f-web/.*',
                           r'https://[^/]+/static/errors/nondispo.html', UnavailablePage)

    redirect_page = URL(r'https://[^/]+/portailinternet/_layouts/Ibp.Cyi.Layouts/RedirectSegment.aspx.*', RedirectPage)
    home_page = URL(r'https://[^/]+/portailinternet/Catalogue/Segments/.*.aspx(\?vary=(?P<vary>.*))?',
                    r'https://[^/]+/portailinternet/Pages/.*.aspx\?vary=(?P<vary>.*)',
                    r'https://[^/]+/portailinternet/Pages/default.aspx',
                    r'https://[^/]+/portailinternet/Transactionnel/Pages/CyberIntegrationPage.aspx',
                    HomePage)

    login2_page = URL(r'https://[^/]+/WebSSO_BP/_(?P<bankid>\d+)/index.html\?transactionID=(?P<transactionID>.*)', Login2Page)

    # linebourse
    linebourse_page = URL(r'https://www.linebourse.fr/ReroutageSJR', LineboursePage)
    message_page = URL(r'https://www.linebourse.fr/DetailMessage.*', MessagePage)
    invest_linebourse_page = URL(r'https://www.linebourse.fr/Portefeuille', InvestmentLineboursePage)

    # natixis
    natixis_page = URL(r'https://www.assurances.natixis.fr/espaceinternet-bp/views/common.*', NatixisPage)
    etna = URL(r'https://www.assurances.natixis.fr/etna-ihs-bp/#/contratVie/(?P<id1>\w+)/(?P<id2>\w+)/(?P<id3>\w+).*', EtnaPage)
    natixis_error_page = URL(r'https://www.assurances.natixis.fr/espaceinternet-bp/error-redirect.*',
                             r'https://www.assurances.natixis.fr/etna-ihs-bp/#/equipement;codeEtab=.*\?windowId=.*',
                             NatixisErrorPage)
    natixis_invest = URL(r'https://www.assurances.natixis.fr/espaceinternet-bp/rest/v2/contratVie/load/(?P<id1>\w+)/(?P<id2>\w+)/(?P<id3>\w+)', NatixisInvestPage)
    natixis_history = URL(r'https://www.assurances.natixis.fr/espaceinternet-bp/rest/v2/contratVie/load-operation/(?P<id1>\w+)/(?P<id2>\w+)/(?P<id3>\w+)', NatixisHistoryPage)
    natixis_pdf = URL(r'https://www.assurances.natixis.fr/espaceinternet-bp/rest/v2/contratVie/load-releve/(?P<id1>\w+)/(?P<id2>\w+)/(?P<id3>\w+)/(?P<year>\d+)', NatixisDetailsPage)

    advisor = URL(r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=accueil.*',
                  r'https://[^/]+/cyber/internet/StartTask.do\?taskInfoOID=contacter.*', AdvisorPage)

    def __init__(self, website, *args, **kwargs):
        self.BASEURL = 'https://%s' % website
        self.token = None

        super(BanquePopulaire, self).__init__(*args, **kwargs)

    #def home(self):
    #    self.do_login()

    no_login = 0

    @no_need_login
    def do_login(self):
        """
        Attempt to log in.
        Note: this method does nothing if we are already logged in.
        """
        assert isinstance(self.username, basestring)
        assert isinstance(self.password, basestring)

        self.location(self.BASEURL)

        self.page.login(self.username, self.password)

        if self.login_page.is_here():
            raise BrowserIncorrectPassword()

    ACCOUNT_URLS = ['mesComptes', 'mesComptesPRO', 'maSyntheseGratuite', 'accueilSynthese', 'equipementComplet']

    @need_login
    def go_on_accounts_list(self):
        for taskInfoOID in self.ACCOUNT_URLS:
            data = OrderedDict([('taskInfoOID', taskInfoOID), ('token', self.token)])
            self.location(self.absurl('/cyber/internet/StartTask.do?%s' % urllib.urlencode(data), base=True))
            if not self.page.is_error():
                if self.page.pop_up():
                    self.logger.debug('Popup displayed, retry')
                    data = OrderedDict([('taskInfoOID', taskInfoOID), ('token', self.token)])
                    self.location('/cyber/internet/StartTask.do?%s' % urllib.urlencode(data))
                self.ACCOUNT_URLS = [taskInfoOID]
                break
        else:
            raise BrokenPageError('Unable to go on the accounts list page')

        if self.page.is_short_list():
            form = self.page.get_form(nr=0)
            form['dialogActionPerformed'] = 'EQUIPEMENT_COMPLET'
            form['token'] = self.page.build_token(form['token'])
            form.submit()

    @retry(LoggedOut)
    @need_login
    def get_accounts_list(self, get_iban=True):
        # We have to parse account list in 2 different way depending if we want the iban number or not
        # thanks to stateful website
        self.go_on_accounts_list()

        next_pages = []
        accounts = []

        for a in self.page.iter_accounts(next_pages):
            if get_iban:
                accounts.append(a)
            else:
                yield a

        while len(next_pages) > 0:
            next_page = next_pages.pop()

            if not self.accounts_full_page.is_here():
                self.go_on_accounts_list()
            # If there is an action needed to go to the "next page", do it.
            if 'prevAction' in next_page:
                params = self.page.get_params()
                params['dialogActionPerformed'] = next_page.pop('prevAction')
                params['token'] = self.page.build_token(self.token)
                self.location('/cyber/internet/ContinueTask.do', data=params)

            next_page['token'] = self.page.build_token(self.token)
            self.location('/cyber/internet/ContinueTask.do', data=next_page)

            for a in self.page.iter_accounts(next_pages):
                if get_iban:
                    accounts.append(a)
                else:
                    yield a

        if get_iban:
            for a in accounts:
                a.iban = self.get_iban_number(a)
                yield a

    @need_login
    def get_iban_number(self, account):
        url = self.absurl('/cyber/internet/StartTask.do?taskInfoOID=cyberIBAN&token=%s' % self.page.build_token(self.token), base=True)
        self.location(url)
        # Sometimes we can't choose an account
        if account.type in [Account.TYPE_LIFE_INSURANCE, Account.TYPE_MARKET] or (self.page.need_to_go() and not self.page.go_iban(account)):
            return NotAvailable
        return self.page.get_iban(account.id)

    @retry(LoggedOut)
    @need_login
    def get_account(self, id):
        assert isinstance(id, basestring)

        for a in self.get_accounts_list(False):
            if a.id == id:
                return a

        return None

    @retry(LoggedOut)
    @need_login
    def get_history(self, account, coming=False):
        account = self.get_account(account.id)

        if account._invest_params:
            for tr in self.get_invest_history(account):
                yield tr
            return

        if coming:
            params = account._coming_params
        else:
            params = account._params

        if params is None:
            return

        params['token'] = self.page.build_token(params['token'])

        self.location(self.absurl('/cyber/internet/ContinueTask.do', base=True), data=params)

        if not self.page or self.page.no_operations():
            return

        # Sort by values dates (see comment in TransactionsPage.get_history)
        if len(self.page.doc.xpath('//a[@id="tcl4_srt"]')) > 0:
            form = self.page.get_form(id='myForm')
            form.url = self.absurl('/cyber/internet/Sort.do?property=tbl1&sortBlocId=blc2&columnName=dateValeur')
            params['token'] = self.page.build_token(params['token'])
            form.submit()

        while True:
            assert self.transactions_page.is_here()

            for tr in self.page.get_history(account, coming):
                yield tr

            next_params = self.page.get_next_params()
            if next_params is None:
                return

            self.location('/cyber/internet/Page.do?%s' % urllib.urlencode(next_params))

    @need_login
    def go_investments(self, account):
        if not account._invest_params:
            raise NotImplementedError()

        account = self.get_account(account.id)
        params = account._invest_params
        params['token'] = self.page.build_token(params['token'])
        self.location(self.absurl('/cyber/internet/ContinueTask.do', base=True), data=params)

        if self.error_page.is_here():
            raise NotImplementedError()

        url, params = self.page.get_investment_page_params()
        if params:
            self.location(url, data=params)
            if self.linebourse_page.is_here():
                self.location('https://www.linebourse.fr/Portefeuille')
                while self.message_page.is_here():
                    self.page.skip()
                    self.location('https://www.linebourse.fr/Portefeuille')
            elif self.natixis_page.is_here():
                self.page.submit_form()

            if self.natixis_error_page.is_here():
                self.logger.warning("natixis site doesn't work")
                return False
            assert self.etna.is_here()
            return True

    @retry(LoggedOut)
    @need_login
    def get_investment(self, account):
        if not self.go_investments(account):
            return iter([])

        if self.etna.is_here():
            self.natixis_invest.go(**self.page.params)
        return self.page.get_investments()

    @need_login
    def get_invest_history(self, account):
        if not self.go_investments(account):
            return
        if self.etna.is_here():
            params = self.page.params
            self.natixis_history.go(**params)
            items_from_json = list(self.page.get_history())
            items_from_json.sort(reverse=True, key=lambda item: item.date)

            years = list(set(item.date.year for item in items_from_json))
            years.sort(reverse=True)

            for year in years:
                try:
                    self.natixis_pdf.go(year=year, **params)
                except HTTPNotFound:
                    self.logger.debug('no pdf for year %s, fallback on json transactions', year)
                    for tr in items_from_json:
                        if tr.date.year == year:
                            yield tr
                else:
                    history = list(self.page.get_history())
                    history.sort(reverse=True, key=lambda item: item.date)
                    for tr in history:
                        yield tr

    @retry(LoggedOut)
    @need_login
    def get_advisor(self):
        for taskInfoOID in ['accueil', 'contacter']:
            data = OrderedDict([('taskInfoOID', taskInfoOID), ('token', self.token)])
            self.location(self.absurl('/cyber/internet/StartTask.do?%s' % urllib.urlencode(data), base=True))
            if taskInfoOID == "accueil":
                advisor = self.page.get_advisor()
                if not advisor:
                    break
            else:
                self.page.update_agency(advisor)
        return iter([advisor])


class iter_retry(object):
    # when the callback is retried, it will create a new iterator, but we may already yielded
    # some values, so we need to keep track of them and seek in the middle of the iterator

    def __init__(self, cb, remaining=4, value=None, exc_check=Exception, logger=None):
        self.cb = cb
        self.it = value
        self.items = []
        self.remaining = remaining
        self.exc_check = exc_check
        self.logger = logger

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining <= 0:
            raise BrowserUnavailable('Site did not reply successfully after multiple tries')

        if self.it is None:
            self.it = self.cb()

            # recreated iterator, consume previous items
            try:
                nb = -1
                for nb, sent in enumerate(self.items):
                    new = next(self.it)
                    if hasattr(new, 'to_dict'):
                        equal = sent.to_dict() == new.to_dict()
                    else:
                        equal = sent == new
                    if not equal:
                        # safety is not guaranteed
                        raise BrowserUnavailable('Site replied inconsistently between retries, %r vs %r', sent, new)
            except StopIteration:
                raise BrowserUnavailable('Site replied fewer elements (%d) than last iteration (%d)', nb + 1, len(self.items))
            except self.exc_check as exc:
                if self.logger:
                    self.logger.info('%s raised, retrying', exc)
                self.it = None
                self.remaining -= 1
                return next(self)

        # return one item
        try:
            obj = next(self.it)
        except self.exc_check as exc:
            if self.logger:
                self.logger.info('%s raised, retrying', exc)
            self.it = None
            self.remaining -= 1
            return next(self)
        else:
            self.items.append(obj)
            return obj

    next = __next__

