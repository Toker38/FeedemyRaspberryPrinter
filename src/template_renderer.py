"""
Template Renderer
JSON template → ESC/POS bytes
"""

import json
import re
import logging
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from templates.escpos_commands import (
    INIT, LF, SELECT_CHARSET,
    BOLD_ON, BOLD_OFF,
    NORMAL, ALIGN_LEFT, ALIGN_CENTER,
    CUT_FULL, CUT_PARTIAL,
    feed_lines, get_size_command, get_align_command,
    encode_turkish
)

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """JSON template'i ESC/POS byte'larına çevirir"""

    def __init__(self, default_width: int = 48):
        self.default_width = default_width

    def render(self, template_json: str, data_json: str) -> bytes:
        """
        Template ve data'yı birleştirip ESC/POS bytes döndür

        Args:
            template_json: Template JSON string
            data_json: PrintData JSON string (sipariş verisi)

        Returns:
            ESC/POS byte sequence
        """
        try:
            template = json.loads(template_json)
            data = json.loads(data_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return self._render_error("JSON Parse Error")

        width = template.get("width", self.default_width)
        elements = template.get("elements", [])

        # Printer'ı initialize et
        output = bytearray()
        output.extend(INIT)
        output.extend(SELECT_CHARSET)

        # Her elementi render et
        for element in elements:
            # Conditional check
            cond = element.get("cond")
            if cond and not self._check_condition(cond, data):
                continue

            elem_type = element.get("t", "text")
            rendered = self._render_element(elem_type, element, data, width)
            output.extend(rendered)

        return bytes(output)

    def _check_condition(self, cond: str, data: dict) -> bool:
        """
        Condition kontrolü
        cond = "fieldName" → data'da fieldName varsa ve truthy ise True
        """
        value = self._get_nested_value(data, cond)
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        if isinstance(value, list):
            return len(value) > 0
        return True

    def _get_nested_value(self, data: dict, key: str) -> Any:
        """
        Nested key erişimi: "order.items" → data["order"]["items"]
        """
        keys = key.split(".")
        value = data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        return value

    def _replace_placeholders(self, text: str, data: dict) -> str:
        """
        {{placeholder}} değerlerini data'dan al
        """
        def replacer(match):
            key = match.group(1)
            value = self._get_nested_value(data, key)
            if value is None:
                return ""
            return str(value)

        return re.sub(r'\{\{(\w+(?:\.\w+)*)\}\}', replacer, text)

    def _render_element(self, elem_type: str, element: dict, data: dict, width: int) -> bytes:
        """Element tipine göre render et"""
        if elem_type == "text":
            return self._render_text(element, data)
        elif elem_type == "line":
            return self._render_line(element, width)
        elif elem_type == "row":
            return self._render_row(element, data, width)
        elif elem_type == "feed":
            return self._render_feed(element)
        elif elem_type == "items":
            return self._render_items(element, data, width)
        elif elem_type == "cut":
            return self._render_cut(element)
        else:
            logger.warning(f"Unknown element type: {elem_type}")
            return b""

    def _render_text(self, element: dict, data: dict) -> bytes:
        """Text elementi render et"""
        output = bytearray()

        # Alignment
        align = element.get("a", "l")
        output.extend(get_align_command(align))

        # Size
        size = element.get("s", "md")
        output.extend(get_size_command(size))

        # Bold
        if element.get("b", False):
            output.extend(BOLD_ON)

        # Text
        text = element.get("v", "")
        text = self._replace_placeholders(text, data)
        output.extend(encode_turkish(text))
        output.extend(LF)

        # Reset
        if element.get("b", False):
            output.extend(BOLD_OFF)
        output.extend(NORMAL)
        output.extend(ALIGN_LEFT)

        return bytes(output)

    def _render_line(self, element: dict, width: int) -> bytes:
        """Yatay çizgi render et"""
        char = element.get("c", "-")
        line = char * width
        output = bytearray()
        output.extend(encode_turkish(line))
        output.extend(LF)
        return bytes(output)

    def _render_row(self, element: dict, data: dict, width: int) -> bytes:
        """Sol-sağ hizalı satır render et"""
        output = bytearray()

        # Size
        size = element.get("s", "md")
        output.extend(get_size_command(size))

        # Bold
        if element.get("b", False):
            output.extend(BOLD_ON)

        left = self._replace_placeholders(element.get("l", ""), data)
        right = self._replace_placeholders(element.get("r", ""), data)

        # Genişliği hesapla (size'a göre ayarla)
        effective_width = width
        if size in ["lg", "xl"]:
            effective_width = width // 2  # Double width'de karakter sayısı yarıya düşer

        # Boşluk hesapla
        spaces = effective_width - len(left) - len(right)
        if spaces < 1:
            spaces = 1

        row_text = left + (" " * spaces) + right
        output.extend(encode_turkish(row_text))
        output.extend(LF)

        # Reset
        if element.get("b", False):
            output.extend(BOLD_OFF)
        output.extend(NORMAL)

        return bytes(output)

    def _render_feed(self, element: dict) -> bytes:
        """Satır boşluğu"""
        n = element.get("n", 1)
        return feed_lines(n)

    def _render_items(self, element: dict, data: dict, width: int) -> bytes:
        """Ürün listesi render et - tam destek: option fiyat, addon miktar, subItems"""
        output = bytearray()

        items = data.get("items", [])
        show_qty = element.get("showQuantity", True)
        show_price = element.get("showPrice", True)
        show_addons = element.get("showAddons", True)
        show_sub_items = element.get("showSubItems", True)
        show_notes = element.get("showNotes", True)
        show_removed = element.get("showRemovedIngredients", False)
        show_option = element.get("showSelectedOption", True)

        font_size = element.get("fontSize", "md")
        addon_prefix = element.get("addonPrefix", "  + ")
        sub_item_prefix = element.get("subItemPrefix", "  > ")
        note_prefix = element.get("notePrefix", "  * ")
        removed_prefix = element.get("removedPrefix", "  - CIKART: ")

        output.extend(get_size_command(font_size))

        for item in items:
            # === ANA URUN SATIRI ===
            qty = item.get("quantity", 1)
            name = item.get("productName", item.get("name", ""))
            price = item.get("unitPrice", item.get("price", 0))

            output.extend(BOLD_ON)

            if show_qty and show_price:
                left = f"{qty}x {name}"
                right = f"{price:.2f}"
                spaces = width - len(left) - len(right)
                if spaces < 1:
                    spaces = 1
                line = left + (" " * spaces) + right
            elif show_qty:
                line = f"{qty}x {name}"
            elif show_price:
                line = f"{name}  {price:.2f}"
            else:
                line = name

            output.extend(encode_turkish(line))
            output.extend(LF)
            output.extend(BOLD_OFF)

            # === SECILEN OPSIYON (fiyat dahil) ===
            if show_option:
                selected_option = item.get("selectedOption")
                option_price = item.get("selectedOptionPrice", 0)
                if selected_option:
                    if isinstance(selected_option, dict):
                        opt_name = selected_option.get("optionName", "")
                        option_price = selected_option.get("priceModifier", option_price)
                    else:
                        opt_name = str(selected_option)

                    if opt_name:
                        if show_price and option_price and option_price != 0:
                            sign = "+" if option_price > 0 else ""
                            output.extend(encode_turkish(f"  ({opt_name} {sign}{option_price:.2f})"))
                        else:
                            output.extend(encode_turkish(f"  ({opt_name})"))
                        output.extend(LF)

            # === CIKARILAN MALZEMELER (belirgin sekilde) ===
            if show_removed:
                removed = item.get("removedIngredients", [])
                # removedIngredientsText varsa onu kullan (hazir formatli)
                removed_text = item.get("removedIngredientsText")
                if removed_text:
                    output.extend(BOLD_ON)
                    output.extend(encode_turkish(f"  {removed_text}"))
                    output.extend(LF)
                    output.extend(BOLD_OFF)
                elif removed:
                    output.extend(BOLD_ON)
                    ing_names = []
                    for ing in removed:
                        if isinstance(ing, dict):
                            ing_names.append(ing.get("ingredientName", ing.get("name", "")))
                        else:
                            ing_names.append(str(ing))
                    if ing_names:
                        output.extend(encode_turkish(f"{removed_prefix}{', '.join(ing_names)}"))
                        output.extend(LF)
                    output.extend(BOLD_OFF)

            # === EKLENTILER (Addons) - miktar ve fiyat dahil ===
            if show_addons:
                addons = item.get("addons", [])
                for addon in addons:
                    addon_name = addon.get("addonName", addon.get("name", ""))
                    addon_qty = addon.get("quantity", addon.get("quantityPerParent", 1))
                    addon_unit_price = addon.get("unitPrice", addon.get("price", 0))
                    addon_line_total = addon.get("lineTotal", addon_unit_price * addon_qty)
                    related_option = addon.get("relatedOptionName")

                    # Addon satiri olustur
                    if addon_qty > 1:
                        addon_text = f"{addon_prefix}{addon_qty}x {addon_name}"
                    else:
                        addon_text = f"{addon_prefix}{addon_name}"

                    # İliskili opsiyon varsa ekle
                    if related_option:
                        addon_text += f" ({related_option})"

                    # Fiyat ekle
                    if show_price and addon_line_total > 0:
                        addon_text += f"  +{addon_line_total:.2f}"

                    output.extend(encode_turkish(addon_text))
                    output.extend(LF)

            # === SET MENU ALT OGELERI (SubItems) ===
            if show_sub_items:
                sub_items = item.get("subItems", [])
                for sub in sub_items:
                    sub_title = sub.get("displayTitle", "")
                    sub_name = sub.get("itemName", sub.get("name", ""))
                    sub_qty = sub.get("quantity", sub.get("quantityPerParent", 1))
                    sub_additional_price = sub.get("additionalPrice", 0)

                    # SubItem satiri
                    if sub_title:
                        sub_text = f"{sub_item_prefix}{sub_title}: "
                    else:
                        sub_text = f"{sub_item_prefix}"

                    if sub_qty > 1:
                        sub_text += f"{sub_qty}x {sub_name}"
                    else:
                        sub_text += sub_name

                    if show_price and sub_additional_price > 0:
                        sub_text += f"  +{sub_additional_price:.2f}"

                    output.extend(encode_turkish(sub_text))
                    output.extend(LF)

                    # SubItem cikarilan malzemeler
                    if show_removed:
                        sub_removed_text = sub.get("removedIngredientsText")
                        sub_removed = sub.get("removedIngredients", [])
                        if sub_removed_text:
                            output.extend(BOLD_ON)
                            output.extend(encode_turkish(f"    {sub_removed_text}"))
                            output.extend(LF)
                            output.extend(BOLD_OFF)
                        elif sub_removed:
                            output.extend(BOLD_ON)
                            sub_ing_names = [str(ing) if not isinstance(ing, dict) else ing.get("ingredientName", "") for ing in sub_removed]
                            if sub_ing_names:
                                output.extend(encode_turkish(f"    {removed_prefix}{', '.join(sub_ing_names)}"))
                                output.extend(LF)
                            output.extend(BOLD_OFF)

                    # SubItem addonlari
                    if show_addons:
                        sub_addons = sub.get("addons", [])
                        for sub_addon in sub_addons:
                            sa_name = sub_addon.get("addonName", sub_addon.get("name", ""))
                            sa_qty = sub_addon.get("quantity", sub_addon.get("quantityPerParent", 1))
                            sa_price = sub_addon.get("lineTotal", sub_addon.get("unitPrice", 0))

                            if sa_qty > 1:
                                sa_text = f"    {addon_prefix}{sa_qty}x {sa_name}"
                            else:
                                sa_text = f"    {addon_prefix}{sa_name}"

                            if show_price and sa_price > 0:
                                sa_text += f"  +{sa_price:.2f}"

                            output.extend(encode_turkish(sa_text))
                            output.extend(LF)

            # === URUN NOTU ===
            if show_notes:
                item_note = item.get("note")
                if item_note:
                    output.extend(encode_turkish(f"{note_prefix}{item_note}"))
                    output.extend(LF)

            # Urunler arasi bosluk
            output.extend(LF)

        output.extend(NORMAL)
        return bytes(output)

    def _render_cut(self, element: dict) -> bytes:
        """Kağıt kesimi"""
        partial = element.get("partial", False)
        return CUT_PARTIAL if partial else CUT_FULL

    def _render_error(self, message: str) -> bytes:
        """Hata durumunda basit fiş"""
        output = bytearray()
        output.extend(INIT)
        output.extend(ALIGN_CENTER)
        output.extend(BOLD_ON)
        output.extend(encode_turkish("=== HATA ==="))
        output.extend(LF)
        output.extend(BOLD_OFF)
        output.extend(encode_turkish(message))
        output.extend(LF)
        output.extend(feed_lines(3))
        output.extend(CUT_FULL)
        return bytes(output)
