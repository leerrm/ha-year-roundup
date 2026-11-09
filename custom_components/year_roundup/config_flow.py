"""Config + options flow for Year Roundup."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import CONF_AI_ENTITY, CONF_STYLE, DEFAULT_STYLE, DOMAIN


def _schema(options: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_AI_ENTITY,
                description={"suggested_value": options.get(CONF_AI_ENTITY)},
            ): EntitySelector(EntitySelectorConfig(domain="ai_task")),
            vol.Optional(
                CONF_STYLE, default=options.get(CONF_STYLE, DEFAULT_STYLE)
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
    )


class YearRoundupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup: AI agent is optional."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Year Roundup", data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return YearRoundupOptionsFlow()


class YearRoundupOptionsFlow(OptionsFlow):
    """Change or remove the AI agent and its style prompt."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=_schema(dict(self.config_entry.options))
        )
