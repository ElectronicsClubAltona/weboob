# -*- coding: utf-8 -*-

# Copyright(C) 2010-2011  Nicolas Duhamel
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


from io import BytesIO
import re
from urlparse import urljoin

from weboob.capabilities.base import NotAvailable
from weboob.capabilities.bank import Account
from weboob.capabilities.contact import Advisor
from weboob.browser.elements import ListElement, ItemElement, method
from weboob.browser.pages import LoggedPage, RawPage, PartialHTMLPage, HTMLPage
from weboob.browser.filters.html import Link
from weboob.browser.filters.standard import CleanText, CleanDecimal, Regexp, Env, Field, BrowserURL, Currency
from weboob.exceptions import BrowserUnavailable

from .base import MyHTMLPage


class AccountList(LoggedPage, MyHTMLPage):
    def on_load(self):
        MyHTMLPage.on_load(self)

        if self.doc.xpath(u'//h2[text()="ERREUR"]'): # website sometime crash
            self.browser.location('https://voscomptesenligne.labanquepostale.fr/voscomptes/canalXHTML/securite/authentification/initialiser-identif.ea')

            raise BrowserUnavailable()

    @property
    def no_accounts(self):
        return len(self.doc.xpath('//iframe[contains(@src, "/comptes_contrats/sans_")]')) > 0

    @method
    class iter_accounts(ListElement):
        item_xpath = u'//ul/li//div[contains(@class, "account-resume")]'

        class item(ItemElement):
            klass = Account

            def condition(self):
                return len(self.el.xpath('.//span[@class="number"]')) > 0

            obj_id = CleanText('.//abbr/following-sibling::text()')
            obj_currency = Currency('.//span[@class="number"]')

            def obj__link_id(self):
                url = Link(u'./a', default=NotAvailable)(self)
                if url:
                    return urljoin(self.page.url, url)
                return url

            def obj_label(self):
                return CleanText('.//div[@class="title"]/h3')(self).upper()

            def obj_balance(self):
                if Field('type')(self) == Account.TYPE_LOAN:
                    return -abs(CleanDecimal('.//span[@class="number"]', replace_dots=True)(self))
                return CleanDecimal('.//span[@class="number"]', replace_dots=True, default=NotAvailable)(self)

            def obj_coming(self):
                if Field('type')(self) == Account.TYPE_CHECKING:
                    has_coming = False
                    coming = 0

                    coming_operations = self.page.browser.open(BrowserURL('par_account_checking_coming', accountId=Field('id'))(self))

                    if CleanText('//span[@id="amount_total"]')(coming_operations.page.doc):
                        has_coming = True
                        coming += CleanDecimal('//span[@id="amount_total"]', replace_dots=True)(coming_operations.page.doc)

                    if CleanText(u'.//dt[contains(., "Débit différé à débiter")]')(self):
                        has_coming = True
                        coming += CleanDecimal(u'.//dt[contains(., "Débit différé à débiter")]/following-sibling::dd[1]', replace_dots=True)(self)

                    return coming if has_coming else NotAvailable
                return NotAvailable

            def obj_iban(self):
                response = self.page.browser.open('/voscomptes/canalXHTML/comptesCommun/imprimerRIB/init-imprimer_rib.ea?compte.numero=%s' % Field('id')(self))

                return response.page.get_iban()

            def obj_type(self):
                type = Regexp(CleanText('../../preceding-sibling::div[@class="avoirs"][1]/span[1]'), r'(\d+) (.*)', '\\2')(self)
                types = {'comptes? bancaires?': Account.TYPE_CHECKING,
                         'livrets?': Account.TYPE_SAVINGS,
                         'epargnes? logement': Account.TYPE_SAVINGS,
                         'comptes? titres? et pea': Account.TYPE_MARKET,
                         'assurances? vie et retraite': Account.TYPE_LIFE_INSURANCE,
                         u'prêt': Account.TYPE_LOAN,
                         u'crédits?': Account.TYPE_LOAN,
                        }

                for atypetxt, atype in types.iteritems():
                    if re.findall(atypetxt, type.lower()): # match with/without plurial in type
                        return atype

                return Account.TYPE_UNKNOWN

            def obj__has_cards(self):
                return Link(u'.//a[contains(., "Débit différé")]', default=None)(self)


class Advisor(LoggedPage, MyHTMLPage):
    @method
    class get_advisor(ItemElement):
        klass = Advisor

        obj_name = Env('name')
        obj_phone = Env('phone')
        obj_mobile = Env('mobile', default=NotAvailable)
        obj_agency = Env('agency', default=NotAvailable)
        obj_email = NotAvailable

        def obj_address(self):
            return CleanText('//div[h3[contains(text(), "Bureau")]]/div[not(@class)][position() > 1]')(self) or NotAvailable

        def parse(self, el):
            # we have two kinds of page and sometimes we don't have any advisor
            agency_phone = CleanText('//span/a[contains(@href, "rendezVous")]', replace=[(' ', '')], default=NotAvailable)(self) or \
                           CleanText('//div[has-class("lbp-numero")]/span', replace=[(' ', '')], default=NotAvailable)(self)
            advisor_phone = Regexp(CleanText('//div[h3[contains(text(), "conseil")]]//span[2]', replace=[(' ', '')], default=""), '(\d+)', default="")(self)
            if advisor_phone.startswith(("06", "07")):
                self.env['phone'] = agency_phone
                self.env['mobile'] = advisor_phone
            else:
                self.env['phone'] = advisor_phone or agency_phone

            agency = CleanText('//div[h3[contains(text(), "Bureau")]]/div[not(@class)][1]')(self) or NotAvailable
            name = CleanText('//div[h3[contains(text(), "conseil")]]//span[1]', default=None)(self) or \
                   CleanText('//div[@class="lbp-font-accueil"]/div[2]/div[1]/span[1]', default=None)(self)
            if name:
                self.env['name'] = name
                self.env['agency'] = agency
            else:
                self.env['name'] = agency


class AccountRIB(LoggedPage, RawPage):
    iban_regexp = r'BankIdentiferCode(\w+)PSS'

    def __init__(self, *args, **kwargs):
        super(AccountRIB, self).__init__(*args, **kwargs)

        self.parsed_text = ''

        try:
            try:
                from pdfminer.pdfdocument import PDFDocument
                from pdfminer.pdfpage import PDFPage
                newapi = True
            except ImportError:
                from pdfminer.pdfparser import PDFDocument
                newapi = False
            from pdfminer.pdfparser import PDFParser, PDFSyntaxError
            from pdfminer.converter import TextConverter
            from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
        except ImportError:
            self.logger.warning('Please install python-pdfminer to get IBANs')
        else:
            parser = PDFParser(BytesIO(self.doc))
            try:
                if newapi:
                    doc = PDFDocument(parser)
                else:
                    doc = PDFDocument()
                    parser.set_document(doc)
                    doc.set_parser(parser)
            except PDFSyntaxError:
                return

            rsrcmgr = PDFResourceManager()
            out = BytesIO()
            device = TextConverter(rsrcmgr, out)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            if newapi:
                pages = PDFPage.create_pages(doc)
            else:
                doc.initialize()
                pages = doc.get_pages()
            for page in pages:
                interpreter.process_page(page)

            self.parsed_text = out.getvalue()

    def get_iban(self):
        m = re.search(self.iban_regexp, self.parsed_text)
        if m:
            return unicode(m.group(1))
        return None


class MarketLoginPage(LoggedPage, PartialHTMLPage):
    def on_load(self):
        self.get_form(id='autoSubmit').submit()


class UselessPage(LoggedPage, HTMLPage):
    pass
