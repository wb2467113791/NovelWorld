package org.novelworld.world;

import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class WorldObjectsTest {
    final WorldRules rules = new WorldRules();
    final ObjectMapper mapper = new ObjectMapper();
    final Map<String, Object> world = new LinkedHashMap<>();
    final Map<String, Object> book;
    final Map<String, Object> chest;
    final Map<String, Object> door;
    final Map<String, Object> key;

    WorldObjectsTest() {
        var characters = new LinkedHashMap<String, Object>();
        for (String name : List.of("甲", "乙", "丙")) {
            var person = new LinkedHashMap<String, Object>();
            person.put("name", name); person.put("location", name.equals("丙") ? "外院" : "客栈");
            person.put("energy", 100); person.put("hp", 60); person.put("status", "normal");
            person.put("items", new ArrayList<>()); person.put("relationships", new LinkedHashMap<>());
            characters.put(name, person);
        }
        world.put("characters", characters); world.put("locations", List.of("客栈", "外院"));
        world.put("inspectables", Map.of("客栈", "整洁", "外院", "空旷"));
        world.put("inspectable_objects", Map.of("客栈", Map.of("登记簿", "已核对内容", "木箱", "普通木箱", "后门", "门", "钥匙", "小钥匙")));
        world.put("events", new ArrayList<>()); world.put("time", "08:00"); world.put("revision", 0);
        WorldObjects.ensure(world);
        book = named("登记簿"); chest = named("木箱"); door = named("后门"); key = named("钥匙");
    }
    Map<String, Object> named(String name) {
        return WorldObjects.map(world.get("objects")).values().stream().map(WorldObjects::map)
                .filter(item -> name.equals(item.get("name"))).findFirst().orElseThrow();
    }
    void act(String tool, String actor, Map<String, Object> item, Object... extra) {
        var args = new LinkedHashMap<String, Object>(); args.put("character", actor); args.put("object_id", item.get("id"));
        for (int i = 0; i < extra.length; i += 2) args.put((String) extra[i], extra[i + 1]);
        rules.apply(world, tool, args);
    }
    void reject(String tool, String actor, Map<String, Object> item, Object... extra) {
        WorldObjects.ensure(world);
        String before = mapper.writeValueAsString(world);
        assertThrows(IllegalArgumentException.class, () -> act(tool, actor, item, extra));
        assertEquals(before, mapper.writeValueAsString(world), "拒绝不能修改状态或生成事件");
    }
    Map<String, Object> person(String actor) { return WorldObjects.map(WorldObjects.map(world.get("characters")).get(actor)); }
    void open() { act("interact", "甲", chest, "action", "open"); }
    void inside() { act("take", "甲", book); open(); act("put", "甲", book, "container_id", chest.get("id")); }

    @Test void stableMigrationAndDisplayNamesAreNotPrimaryKeys() {
        String id = (String) book.get("id"); book.put("name", "改名的书"); WorldObjects.ensure(world);
        assertEquals(id, book.get("id"));
        var second = WorldObjects.object("another-id", "改名的书", "客栈", "另一册");
        WorldObjects.map(world.get("objects")).put("another-id", second); WorldObjects.validate(world);
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "inspect", Map.of("character", "甲", "object_name", "改名的书")));
        act("inspect", "甲", second);
        assertEquals("obj-" + WorldObjects.stableId("scene\0客栈\0登记簿").substring(4), id);
    }
    @Test void inspectHasPrivateVerifiedResult() {
        act("inspect", "甲", book);
        var event = WorldObjects.map(WorldObjects.list(world.get("events")).get(0));
        assertEquals(List.of("甲"), event.get("perceived_by"));
        assertEquals(book.get("id"), WorldObjects.map(event.get("payload")).get("object_id"));
        assertTrue(event.get("description").toString().contains("已核对内容"));
        reject("inspect", "甲", book);
    }
    @Test void hiddenInspectIsRejected() { book.put("visible", false); reject("inspect", "甲", book); }
    @Test void distantInspectIsRejected() { reject("inspect", "丙", book); }
    @Test void missingObjectAndActorAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "take", Map.of("character", "甲", "object_id", "missing")));
        reject("take", "missing", book);
    }
    @Test void takeChangesOnlyHolderAndPreservesOwner() {
        book.put("owner", "乙"); act("take", "甲", book);
        assertEquals("甲", book.get("holder")); assertEquals("乙", book.get("owner"));
        assertNull(book.get("location")); assertNull(book.get("container"));
        assertEquals(List.of("登记簿"), person("甲").get("items"));
    }
    @Test void fixedObjectCannotBeTaken() { reject("take", "甲", door); }
    @Test void distantObjectCannotBeTaken() { reject("take", "丙", book); }
    @Test void hiddenObjectCannotBeTaken() { book.put("visible", false); reject("take", "甲", book); }
    @Test void OtherHolderCannotBeRobbedByTake() { act("take", "乙", book); reject("take", "甲", book); }
    @Test void putRequiresHolding() { reject("put", "甲", book, "location", "客栈"); }
    @Test void putOnlyCurrentPlaceAndOneDestination() {
        act("take", "甲", book); reject("put", "甲", book, "location", "外院");
        reject("put", "甲", book, "location", "客栈", "container_id", chest.get("id"));
        act("put", "甲", book, "location", "客栈"); assertNull(book.get("holder")); assertEquals("客栈", book.get("location"));
    }
    @Test void closedContainerRejectsPut() { act("take", "甲", book); reject("put", "甲", book, "container_id", chest.get("id")); }
    @Test void openedContainerAcceptsPut() { inside(); assertEquals(chest.get("id"), book.get("container")); assertNull(book.get("holder")); assertNull(book.get("location")); }
    @Test void wrongOrDistantContainerIsRejected() {
        act("take", "甲", book); reject("put", "甲", book, "container_id", door.get("id"));
        reject("put", "甲", book, "container_id", "missing");
        open(); chest.put("location", "外院"); reject("put", "甲", book, "container_id", chest.get("id"));
    }
    @Test void closedContentsStayHiddenUntilOpen() {
        inside(); act("interact", "甲", chest, "action", "close");
        assertFalse(WorldObjects.visible(world, book, "乙")); reject("inspect", "乙", book); reject("take", "乙", book);
        act("interact", "乙", chest, "action", "open"); assertTrue(WorldObjects.visible(world, book, "乙"));
        act("inspect", "乙", book); act("take", "乙", book); assertNull(book.get("container"));
    }
    @Test void invisibleContainerHidesContentsEvenWhenOpen() { inside(); chest.put("visible", false); reject("inspect", "乙", book); }
    @Test void giveRequiresSamePlace() { act("take", "甲", key); reject("give", "甲", key, "receiver", "丙"); }
    @Test void giveRequiresHoldingAndRealReceiver() {
        reject("give", "甲", key, "receiver", "乙"); act("take", "甲", key);
        reject("give", "甲", key, "receiver", "missing"); reject("give", "甲", key, "receiver", "甲");
    }
    @Test void giveTransfersExactlyOneHolderAndRetainsOwner() {
        key.put("owner", "甲"); act("take", "甲", key); act("give", "甲", key, "receiver", "乙");
        assertEquals("乙", key.get("holder")); assertEquals("甲", key.get("owner"));
        assertEquals(List.of(), person("甲").get("items")); assertEquals(List.of("钥匙"), person("乙").get("items"));
        var event = WorldObjects.map(WorldObjects.list(world.get("events")).get(1)); assertEquals(List.of("甲", "乙"), event.get("perceived_by"));
    }
    @Test void doorOpensClosesWithDeclaredAffordances() {
        act("interact", "甲", door, "action", "open"); assertEquals("open", door.get("state"));
        reject("interact", "甲", door, "action", "open"); act("interact", "甲", door, "action", "close"); assertEquals("closed", door.get("state"));
    }
    @Test void arbitraryInteractionAndUndeclaredAffordanceAreRejected() {
        reject("interact", "甲", door, "action", "拆门烧毁"); reject("interact", "甲", book, "action", "open");
        door.put("state", "locked"); reject("interact", "甲", door, "action", "open");
    }
    @Test void useIsBoundedAndNotNameBased() { reject("use", "甲", key, "action", "unlock"); reject("use", "甲", book, "action", "consume"); }
    @Test void lampUseValidatesStateAndTool() {
        key.put("affordances", List.of("light", "extinguish")); key.put("state", "extinguished");
        reject("interact", "甲", key, "action", "light"); act("use", "甲", key, "action", "light"); assertEquals("lit", key.get("state"));
        reject("use", "甲", key, "action", "light"); act("use", "甲", key, "action", "extinguish"); assertEquals("extinguished", key.get("state"));
    }
    @Test void medicineConsumesRealHeldObjectOnce() {
        key.put("affordances", List.of("consume")); WorldObjects.map(key.get("properties")).put("heal", 20);
        reject("use", "甲", key, "action", "consume"); act("take", "甲", key); act("use", "甲", key, "action", "consume");
        assertEquals(80, person("甲").get("hp")); assertEquals("consumed", key.get("state")); assertNull(key.get("holder"));
        reject("use", "甲", key, "action", "consume");
    }
    @Test void incapacityAndEnergyAreValidatedBeforeMutation() {
        person("甲").put("energy", 0); reject("take", "甲", book); person("甲").put("energy", 100);
        person("甲").put("status", "unconscious"); reject("take", "甲", book);
    }
    @Test void actionsProduceSingleEventWithObjectIdAndLocalWitnesses() {
        act("take", "甲", book); var event = WorldObjects.map(WorldObjects.list(world.get("events")).get(0));
        assertEquals("take", event.get("type")); assertEquals(List.of("甲", "乙"), event.get("perceived_by"));
        assertEquals(book.get("id"), WorldObjects.map(event.get("payload")).get("object_id")); assertEquals("客栈", event.get("location"));
        assertEquals(1, WorldObjects.list(world.get("events")).size());
    }
    @Test void compatibilityViewsCannotOverrideObjects() {
        act("take", "甲", book); person("甲").put("items", List.of("凭空物件"));
        world.put("inspectable_objects", Map.of("外院", Map.of("登记簿", "伪造"))); WorldObjects.ensure(world);
        assertEquals("甲", book.get("holder")); assertEquals(List.of("登记簿"), person("甲").get("items"));
        assertFalse(world.containsKey("inspectable_objects"));
    }
    @Test void retiredWrappersCannotExecute() {
        act("take", "甲", key);
        String before = mapper.writeValueAsString(world);
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "give_item", Map.of("giver", "甲", "receiver", "乙", "item", "钥匙")));
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "world_action", Map.of("actor", "甲", "action", "interact", "object_id", door.get("id"), "interaction", "open")));
        assertEquals(before, mapper.writeValueAsString(world));
    }
    @Test void invalidPhysicalPositionsAndPropertiesAreRejected() {
        book.put("holder", "甲"); assertThrows(IllegalArgumentException.class, () -> WorldObjects.validate(world)); book.put("holder", null);
        WorldObjects.map(book.get("properties")).put("script", "anything"); assertThrows(IllegalArgumentException.class, () -> WorldObjects.validate(world));
    }
    @Test void invalidIdsPortableContainersAndNestedContainersAreRejected() {
        book.put("id", "mismatch"); assertThrows(IllegalArgumentException.class, () -> WorldObjects.validate(world)); book.put("id", WorldObjects.stableId("scene\0客栈\0登记簿"));
        chest.put("portable", true); assertThrows(IllegalArgumentException.class, () -> WorldObjects.validate(world)); chest.put("portable", false);
        chest.put("location", null); chest.put("container", chest.get("id")); assertThrows(IllegalArgumentException.class, () -> WorldObjects.validate(world));
    }
    @Test void recommendedInspectTakeMovePutAndOtherActorOpenChain() {
        chest.put("location", "外院");  // 场景初始设置：固定容器位于另一地点。
        act("inspect", "甲", book); act("take", "甲", book);
        rules.apply(world, "move_character", Map.of("character", "甲", "location", "外院"));
        assertEquals("外院", WorldObjects.location(world, book));
        open(); act("put", "甲", book, "container_id", chest.get("id")); act("interact", "甲", chest, "action", "close");
        reject("inspect", "丙", book); act("interact", "丙", chest, "action", "open"); act("take", "丙", book);
        assertEquals("丙", book.get("holder"));
    }
}
