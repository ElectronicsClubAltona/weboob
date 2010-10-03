# -*- coding: utf-8 -*-

# Copyright(C) 2009-2010  Romain Bignon
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.


from logging import warning

from weboob.tools.browser import BaseBrowser, BrowserIncorrectPassword
from weboob.backends.bnporc import pages
from .errors import PasswordExpired


__all__ = ['BNPorc']


class BNPorc(BaseBrowser):
    DOMAIN = 'www.secure.bnpparibas.net'
    PROTOCOL = 'https'
    ENCODING = None # refer to the HTML encoding
    PAGES = {'.*identifiant=DOSSIER_Releves_D_Operation.*': pages.AccountsList,
             '.*SAF_ROP.*':                                 pages.AccountHistory,
             '.*Action=SAF_CHM.*':                          pages.ChangePasswordPage,
             '.*NS_AVEET.*':                                pages.AccountComing,
             '.*NS_AVEDP.*':                                pages.AccountPrelevement,
             '.*Action=DSP_VGLOBALE.*':                     pages.LoginPage,
             '.*type=homeconnex.*':                         pages.LoginPage,
             '.*layout=HomeConnexion.*':                    pages.ConfirmPage,
             '.*SAF_CHM_VALID.*':                           pages.ConfirmPage,
            }

    is_logging = False

    def __init__(self, *args, **kwargs):
        self.rotating_password = kwargs.pop('rotating_password', None)
        self.password_changed_cb = kwargs.pop('password_changed_cb', None)
        BaseBrowser.__init__(self, *args, **kwargs)

    def home(self):
        self.location('https://www.secure.bnpparibas.net/banque/portail/particulier/HomeConnexion?type=homeconnex')

    def is_logged(self):
        return not self.is_on_page(pages.LoginPage) or self.is_logging

    def login(self):
        assert isinstance(self.username, basestring)
        assert isinstance(self.password, basestring)
        assert self.password.isdigit()

        if not self.is_on_page(pages.LoginPage):
            self.location('https://www.secure.bnpparibas.net/banque/portail/particulier/HomeConnexion?type=homeconnex')

        self.is_logging = True
        self.page.login(self.username, self.password)
        self.location('/NSFR?Action=DSP_VGLOBALE')

        if self.is_on_page(pages.LoginPage):
            raise BrowserIncorrectPassword()
        self.is_logging = False

    def change_password(self, new_password):
        assert new_password.isdigit() and len(new_password) == 6

        self.location('https://www.secure.bnpparibas.net/SAF_CHM?Action=SAF_CHM')
        assert self.is_on_page(pages.ChangePasswordPage)

        self.page.change_password(self.password, new_password)
        self.password, self.rotating_password = (new_password, self.password)

        if self.password_changed_cb:
            self.password_changed_cb(self.rotating_password, self.password)

    def check_expired_password(func):
        def inner(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except PasswordExpired:
                if self.rotating_password is not None:
                    warning('[%s] Your password has expired. Switching...' % self.username)
                    self.change_password(self.rotating_password)
                    return func(self, *args, **kwargs)
                else:
                    raise
        return inner

    @check_expired_password
    def get_accounts_list(self):
        if not self.is_on_page(pages.AccountsList):
            self.location('/NSFR?Action=DSP_VGLOBALE')

        return self.page.get_list()

    def get_account(self, id):
        assert isinstance(id, (int, long))

        if not self.is_on_page(pages.AccountsList):
            self.location('/NSFR?Action=DSP_VGLOBALE')

        l = self.page.get_list()
        for a in l:
            if long(a.id) == id:
                return a

        return None

    def get_history(self, account):
        if not self.is_on_page(pages.AccountHistory) or self.page.account.id != account.id:
            self.location('/SAF_ROP?ch4=%s' % account.link_id)
        return self.page.get_operations()

    def get_coming_operations(self, account):
        if not self.is_on_page(pages.AccountComing) or self.page.account.id != account.id:
            self.location('/NS_AVEET?ch4=%s' % account.link_id)
        return self.page.get_operations()
