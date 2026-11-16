from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

class ItemEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, item, suffix):
        super().__init__(coordinator)
        self.item_id = item["id"]
        self._attr_unique_id = coordinator.entry.unique_id + "_" + self.item_id + suffix
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.entry.unique_id + "_" + self.item_id)},
            name=item["name"] + " (Beta)", manufacturer="Apple Find My", model=item.get("model") or "Item")
    @property
    def item(self):
        return next((i for i in self.coordinator.data["items"] if i["id"] == self.item_id), {})
    @property
    def available(self):
        return super().available and bool(self.item.get("enabled"))
    @property
    def report(self):
        return self.item.get("report") or {}

async def discover(coordinator, async_add_entities, factory, entry):
    seen = set()
    def update():
        fresh = [i for i in coordinator.data["items"] if i["enabled"] and i["id"] not in seen]
        seen.update(i["id"] for i in fresh)
        async_add_entities([factory(coordinator, i) for i in fresh])
    update()
    entry.async_on_unload(coordinator.async_add_listener(update))
