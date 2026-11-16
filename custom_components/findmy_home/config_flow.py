"""Supervisor discovery and explicit confirmation. No Apple secrets in Core."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .const import DOMAIN, normalize_channel, entry_title
from .api import Api, Unauthorized

class FindMyHomeFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _connection = None

    async def async_step_hassio(self, discovery_info):
        self._connection = dict(discovery_info.config)
        self._connection["app_slug"] = discovery_info.slug
        await self.async_set_unique_id(self._connection["instance_id"])
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": entry_title(self._connection.get("channel"))}
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="hassio_confirm")
        try:
            data = await Api(async_get_clientsession(self.hass), self._connection["host"], self._connection["token"]).snapshot()
            if data["instance_id"] != self._connection["instance_id"]:
                return self.async_abort(reason="wrong_instance")
        except Exception:
            return self.async_show_form(step_id="hassio_confirm", errors={"base":"cannot_connect"})
        self._connection["channel"]=normalize_channel(data.get("channel"))
        return self.async_create_entry(title=entry_title(self._connection["channel"]), data=self._connection)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                data = await Api(async_get_clientsession(self.hass), user_input["host"], user_input["token"]).snapshot()
            except Unauthorized:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            if not errors:
                await self.async_set_unique_id(data["instance_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=entry_title(data.get("channel")), data={**user_input,"instance_id":data["instance_id"],"channel":normalize_channel(data.get("channel"))})
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("host"): str,
            vol.Required("token"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input:
            try:
                data = await Api(async_get_clientsession(self.hass), entry.data["host"], user_input["token"]).snapshot()
                if data["instance_id"] != entry.unique_id:
                    return self.async_abort(reason="wrong_instance")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            except Unauthorized:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reauth_confirm", errors=errors, data_schema=vol.Schema({
            vol.Required("token"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}))
