# -*- coding: utf-8 -*-

# Copyright(C) 2015      Vincent Paredes
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


from weboob.capabilities.bill import Bill, Subscription
from weboob.browser.pages import HTMLPage, LoggedPage, JsonPage
from weboob.browser.filters.standard import CleanDecimal, CleanText, Env, Format, Date
from weboob.browser.filters.html import Attr
from weboob.browser.filters.json import Dict
from weboob.browser.elements import ListElement, ItemElement, method, DictElement


class LoginPage(HTMLPage):
    def is_logged(self):
        return not self.doc.xpath('//div[has-class("error")]')

    def login(self, login, password):
        form = self.get_form('//form[@class="pagination-centered"]')
        user = Attr(None, 'name').filter(self.doc.xpath('//input[contains(@placeholder, "Account ID")]'))
        pwd = Attr(None, 'name').filter(self.doc.xpath('//input[@placeholder="Password"]'))
        form[user] = login
        form[pwd] = password
        form.submit()


class ProfilePage(LoggedPage, JsonPage):
    @method
    class get_list(ListElement):
        class item(ItemElement):
            klass = Subscription

            obj_label = CleanText(Dict('nichandle'))
            obj_subscriber = Format("%s %s", CleanText(Dict('firstname')), CleanText(Dict('name')))
            obj_id = CleanText(Dict('nichandle'))


class BillsPage(LoggedPage, JsonPage):
    @method
    class get_documents(DictElement):
        item_xpath = 'list/results'

        class item(ItemElement):
            klass = Bill

            obj_id = Format('%s.%s', Env('subid'), Dict('orderId'))
            obj_date = Date(Dict('billingDate'))
            obj_format = u"pdf"
            obj_type = u"bill"
            obj_price = CleanDecimal(Dict('priceWithTax/value'))
            obj_url = Dict('pdfUrl')
