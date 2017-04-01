# -*- coding: utf-8 -*-

# Copyright(C) 2012-2013  Romain Bignon
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


import ssl
from datetime import timedelta, date
from urlparse import parse_qs
from lxml.etree import XMLSyntaxError

from weboob.tools.date import LinearDateGuesser
from weboob.capabilities.bank import Account
from weboob.exceptions import BrowserIncorrectPassword
from weboob.browser import LoginBrowser, URL, need_login
from weboob.browser.exceptions import HTTPNotFound

from .pages import AccountsPage, CBOperationPage, CPTOperationPage, LoginPage, AppGonePage, RibPage, LifeInsurancesPage


__all__ = ['HSBC']


class HSBC(LoginBrowser):
    BASEURL = 'https://client.hsbc.fr'
    app_gone = False

    connection =      URL(r'https://www.hsbc.fr/1/2/hsbc-france/particuliers/connexion', LoginPage)
    login =           URL(r'https://www.hsbc.fr/1/*', LoginPage)
    cptPage =         URL(r'/cgi-bin/emcgi.*\&Cpt=.*',
                          r'/cgi-bin/emcgi.*\&Epa=.*',
                          r'/cgi-bin/emcgi.*\&CPT_IdPrestation.*',
                          r'/cgi-bin/emcgi.*\&Ass_IdPrestation.*',
                          CPTOperationPage)
    cbPage =          URL(r'/cgi-bin/emcgi.*\&Cb=.*',
                          r'/cgi-bin/emcgi.*\&CB_IdPrestation.*',
                          CBOperationPage)
    appGone =     URL(r'/.*_absente.html',
                      r'/pm_absent_inter.html',
                      '/appli_absente_MBEL.html',
                        AppGonePage)
    rib =             URL(r'/cgi-bin/emcgi', RibPage)
    accounts =        URL(r'/cgi-bin/emcgi', AccountsPage)

    # separated space
    life_insurances = URL('https://assurances.hsbc.fr/navigation', LifeInsurancesPage)

    def __init__(self, username, password, secret, *args, **kwargs):
        self.accounts_list = dict()
        self.secret = secret

        LoginBrowser.__init__(self, username, password, *args, **kwargs)

    def load_state(self, state):
        return

    def prepare_request(self, req):
        preq = super(HSBC, self).prepare_request(req)

        conn = self.session.adapters['https://'].get_connection(preq.url)
        conn.ssl_version = ssl.PROTOCOL_TLSv1

        return preq

    def do_login(self):
        self.connection.go()
        self.page.login(self.username)

        no_secure_key_link = self.page.get_no_secure_key()

        if not no_secure_key_link:
            raise BrowserIncorrectPassword()
        self.location(no_secure_key_link)

        self.page.login_w_secure(self.password, self.secret)
        for _ in range(2):
            if self.login.is_here():
                self.page.useless_form()

        self.js_url = self.page.get_js_url()
        home_url = self.page.get_frame()

        if not home_url or not self.page.logged:
            raise BrowserIncorrectPassword()

        self.location(home_url)

    @need_login
    def get_accounts_list(self):
        if not self.accounts_list:
            self.update_accounts_list()
        for i, a in self.accounts_list.items():
            yield a

    @need_login
    def update_accounts_list(self):
        for a in list(self.accounts.stay_or_go().iter_accounts()):
            try:
                self.accounts_list[a.id]._link_id = a._link_id
            except KeyError:
                self.accounts_list[a.id] = a

        self.location('%s%s' % (self.page.url, '&debr=COMPTES_RIB'))
        self.page.get_rib(self.accounts_list)

    @need_login
    def _quit_li_space(self):
        if self.life_insurances.is_here():
            self.page.disconnect_order()

            try:
                self.session.cookies.pop('ErisaSession')
                self.session.cookies.pop('HBFR-INSURANCE-COOKIE-82')
            except KeyError:
                pass

            home_url = self.page.get_frame()
            self.js_url = self.page.get_js_url()

            self.location(home_url)

    @need_login
    def _go_to_life_insurance(self, lfid):
        self._quit_li_space()

        url = (self.js_url + 'PLACEMENTS_ASS').split('?')
        data = {}

        for k, v in parse_qs(url[1]).iteritems():
            data[k] = v[0]

        self.location(url[0], data=data).page.redirect_li_space()
        self.life_insurances.go(data={'url_suivant': 'PARTIEGENERIQUEB2C'})

        data = {'url_suivant': 'SITUATIONCONTRATB2C', 'strNumAdh': ''}

        for attr, value in self.page.get_lf_attributes(lfid).iteritems():
            data[attr] = value

        self.life_insurances.go(data=data)

    @need_login
    def get_history(self, account, coming=False):
        if account._link_id is None:
            return

        if account._link_id.startswith('javascript') or '&Crd=' in account._link_id:
            raise NotImplementedError()

        if account.type == Account.TYPE_LIFE_INSURANCE:
            if coming is True:
                raise NotImplementedError()

            try:
                self._go_to_life_insurance(account.id)
            except XMLSyntaxError:
                self.quit_li_space()
                return iter([])

            self.life_insurances.go(data={'url_suivant': 'HISTORIQUECONTRATB2C', 'strMonnaie': 'EURO'})

            history = [t for t in self.page.iter_history()]

            self._quit_li_space()

            return history

        try:
            self.location(self.accounts_list[account.id]._link_id)
        except HTTPNotFound: # sometime go to hsbc life insurance space do logout
            self.app_gone = True

        #If we relogin on hsbc, all link have change
        if self.app_gone:
            self.app_gone = False
            self.update_accounts_list()
            self.location(self.accounts_list[account.id]._link_id)

        if self.page is None:
            return

        if self.cbPage.is_here():
            guesser = LinearDateGuesser(date_max_bump=timedelta(45))
            return [tr for tr in self.page.get_history(date_guesser=guesser) if (coming and tr.date > date.today()) or (not coming and tr.date <= date.today())]
        elif not coming:
            return self._get_history()
        else:
            raise NotImplementedError()

    def _get_history(self):
        for tr in self.page.get_history():
            yield tr

    def get_investments(self, account):
        if account.type != Account.TYPE_LIFE_INSURANCE:
            raise NotImplementedError()

        try:
            self._go_to_life_insurance(account.id)
        except XMLSyntaxError:
            self.quit_li_space()
            return iter([])

        investments = [i for i in self.page.iter_investments()]

        self._quit_li_space()

        return investments
