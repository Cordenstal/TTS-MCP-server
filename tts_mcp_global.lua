-- Tabletop Simulator MCP bridge
-- Install this in the loaded game's Global script.
--
-- If the mod already defines onExternalMessage(data), do not keep the wrapper
-- at the bottom of this file. Instead, call:
--     mcp_handleExternalMessage(data)
-- from the mod's existing onExternalMessage function.

local MCP_CHANNEL = "tts-mcp"
local MCP_HTTP_CHAT_URL = "http://127.0.0.1:8765/chat"
-- `!ai` is interpreted by the HTTP gateway for controls. All chat is sent to
-- the gateway so the configured AI can participate proactively.
-- Empty trigger forwards all player chat to the configured AI backend.
-- Set this to "!ai" if only explicitly addressed messages should be sent.
local MCP_CHAT_TRIGGER = ""

local function mcp_vector(v)
    if v == nil then
        return nil
    end
    return {x = v.x, y = v.y, z = v.z}
end

local function mcp_try(fn)
    local ok, value = pcall(fn)
    if ok then
        return value
    end
    return nil
end

local function mcp_bounds(bounds)
    if type(bounds) ~= "table" then
        return nil
    end
    return {
        center = mcp_vector(bounds.center),
        size = mcp_vector(bounds.size),
        offset = mcp_vector(bounds.offset),
    }
end

local function mcp_zone_guids(obj)
    local zones = mcp_try(function() return obj.getZones() end)
    local guids = {}
    if type(zones) ~= "table" then
        return guids
    end
    for _, zone in ipairs(zones) do
        local guid = mcp_try(function() return zone.getGUID() end)
        if guid ~= nil then
            table.insert(guids, tostring(guid))
        end
    end
    return guids
end

local function mcp_container_items(obj)
    local object_type = tostring(obj.type or "")
    if object_type ~= "Bag" and object_type ~= "Deck" and object_type ~= "Chip" then
        return nil
    end
    local contents = mcp_try(function() return obj.getObjects() end)
    if type(contents) ~= "table" then
        return nil
    end

    local items = {}
    local total = #contents
    local max_items = 200
    for _, item in ipairs(contents) do
        if #items >= max_items then
            break
        end
        if type(item) == "table" then
            table.insert(items, {
                guid = item.guid,
                name = item.name,
                description = item.description,
                index = item.index,
                tags = item.tags,
            })
        end
    end
    return {
        count = #items,
        total = total,
        truncated = total > #items,
        items = items,
    }
end

local function mcp_object_summary(obj)
    local smooth_position = mcp_try(function() return obj.getPositionSmooth() end)
    local smooth_rotation = mcp_try(function() return obj.getRotationSmooth() end)
    return {
        guid = obj.getGUID(),
        name = obj.getName(),
        description = obj.getDescription(),
        type = obj.type,
        tag = obj.tag,
        position = mcp_vector(obj.getPosition()),
        rotation = mcp_vector(obj.getRotation()),
        scale = mcp_vector(obj.getScale()),
        locked = obj.getLock(),
        tags = obj.getTags(),
        quantity = obj.getQuantity(),
        state_id = obj.getStateId(),
        bounds = mcp_bounds(mcp_try(function() return obj.getBounds() end)),
        bounds_normalized = mcp_vector(mcp_try(function() return obj.getBoundsNormalized() end)),
        visual_bounds_normalized = mcp_vector(mcp_try(function() return obj.getVisualBoundsNormalized() end)),
        velocity = mcp_vector(mcp_try(function() return obj.getVelocity() end)),
        angular_velocity = mcp_vector(mcp_try(function() return obj.getAngularVelocity() end)),
        resting = mcp_try(function() return obj.resting end),
        smooth_moving = mcp_try(function() return obj.isSmoothMoving() end),
        smooth_position = mcp_vector(smooth_position),
        smooth_rotation = mcp_vector(smooth_rotation),
        transform_forward = mcp_vector(mcp_try(function() return obj.getTransformForward() end)),
        transform_right = mcp_vector(mcp_try(function() return obj.getTransformRight() end)),
        transform_up = mcp_vector(mcp_try(function() return obj.getTransformUp() end)),
        zone_guids = mcp_zone_guids(obj),
    }
end

-- External Editor callbacks are size-sensitive. AI scene inspection only
-- needs identity, tags, transforms, bounds, and containment; omit volatile
-- velocity/axis metadata so a populated table still returns one response.
local function mcp_compact_object_summary(obj)
    return {
        guid = mcp_try(function() return obj.getGUID() end),
        name = mcp_try(function() return obj.getName() end),
        type = mcp_try(function() return obj.tag end),
        tags = mcp_try(function() return obj.getTags() end) or {},
        position = mcp_vector(mcp_try(function() return obj.getPosition() end)),
        rotation = mcp_vector(mcp_try(function() return obj.getRotation() end)),
        bounds = mcp_bounds(mcp_try(function() return obj.getBounds() end)),
        locked = mcp_try(function() return obj.getLock() end),
        zone_guids = mcp_zone_guids(obj),
    }
end

-- TTS Vector and engine values can be userdata. External Editor responses
-- must contain only JSON primitives/tables or JSON.encode aborts the entire
-- callback after an otherwise successful action.
local function mcp_json_safe(value, depth)
    depth = depth or 0
    if depth > 12 then
        return "<depth-limited>"
    end
    local value_type = type(value)
    if value_type == "nil" or value_type == "boolean" or value_type == "number" or value_type == "string" then
        return value
    end
    if value_type == "userdata" then
        local x = mcp_try(function() return value.x end)
        local y = mcp_try(function() return value.y end)
        local z = mcp_try(function() return value.z end)
        if x ~= nil or y ~= nil or z ~= nil then
            return {x = tonumber(x) or 0, y = tonumber(y) or 0, z = tonumber(z) or 0}
        end
        return tostring(value)
    end
    if value_type == "table" then
        local safe = {}
        for key, item in pairs(value) do
            local key_type = type(key)
            if key_type == "string" or key_type == "number" then
                safe[key] = mcp_json_safe(item, depth + 1)
            end
        end
        return safe
    end
    return tostring(value)
end

local function mcp_send_ok(request_id, result)
    print("[tts-mcp] sending success response for " .. tostring(request_id))
    local response = {
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = true,
        result = mcp_json_safe(result),
    }
    -- Some TTS builds drop sendExternalMessage responses while still sending
    -- ordinary External Editor print callbacks. Emit a compact JSON fallback
    -- on that reliable channel; Python matches it by requestId.
    print("[tts-mcp-response]" .. JSON.encode(response))
    -- Defer the callback until after onExternalMessage returns. This avoids
    -- TTS dropping a nested sendExternalMessage call on some versions.
    Wait.frames(function()
        sendExternalMessage(response)
        print("[tts-mcp] success response sent")
    end, 1)
end

local function mcp_send_error(request_id, err)
    print("[tts-mcp] sending error response for " .. tostring(request_id))
    local response = {
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = false,
        error = tostring(err),
    }
    print("[tts-mcp-response]" .. JSON.encode(response))
    Wait.frames(function()
        sendExternalMessage(response)
        print("[tts-mcp] error response sent")
    end, 1)
end

local function mcp_require_object(guid)
    if type(guid) ~= "string" or guid == "" then
        error("A non-empty object GUID is required.")
    end

    local obj = getObjectFromGUID(guid)
    if obj == nil then
        error("No in-scene object exists with GUID " .. guid)
    end
    return obj
end

local function mcp_has_tag(obj, requested)
    if requested == nil or requested == "" then
        return true
    end

    local wanted = string.lower(tostring(requested))
    for _, actual in ipairs(obj.getTags()) do
        if string.lower(tostring(actual)) == wanted then
            return true
        end
    end
    return false
end

local function mcp_matches_filters(obj, args)
    local name_filter = string.lower(tostring(args.name_contains or ""))
    local tag_filter = tostring(args.tag or "")
    local object_name = string.lower(tostring(obj.getName() or ""))
    return (name_filter == "" or string.find(object_name, name_filter, 1, true) ~= nil)
        and mcp_has_tag(obj, tag_filter)
end

local function mcp_distance_squared(a, b)
    local dx = (a.x or 0) - (b.x or 0)
    local dy = (a.y or 0) - (b.y or 0)
    local dz = (a.z or 0) - (b.z or 0)
    return dx * dx + dy * dy + dz * dz
end

local function mcp_position_from_args(args, prefix)
    local guid_key = prefix .. "_guid"
    local position_key = prefix .. "_position"
    if args[guid_key] ~= nil then
        return mcp_require_object(args[guid_key]).getPosition()
    end
    local position = args[position_key]
    if type(position) ~= "table" then
        error(position_key .. " or " .. guid_key .. " is required.")
    end
    return position
end

local function mcp_region_contains_object(obj, minimum, maximum)
    local bounds = mcp_try(function() return obj.getBounds() end)
    local center = mcp_try(function() return obj.getPosition() end)
    local size = {x = 0, y = 0, z = 0}
    if type(bounds) == "table" then
        center = bounds.center or center
        size = bounds.size or size
    end
    if center == nil then
        return false
    end

    local half = {
        x = math.abs(tonumber(size.x) or 0) / 2,
        y = math.abs(tonumber(size.y) or 0) / 2,
        z = math.abs(tonumber(size.z) or 0) / 2,
    }
    return center.x + half.x >= minimum.x and center.x - half.x <= maximum.x
        and center.y + half.y >= minimum.y and center.y - half.y <= maximum.y
        and center.z + half.z >= minimum.z and center.z - half.z <= maximum.z
end

local MCP_HANDLERS = {}

MCP_HANDLERS.ping = function(args, request_id)
    return {
        bridge = MCP_CHANNEL,
        object_count = #getObjects(),
        message = "Tabletop Simulator MCP bridge is active.",
    }
end

MCP_HANDLERS.list_objects = function(args, request_id)
    local name_filter = string.lower(tostring(args.name_contains or ""))
    local tag_filter = tostring(args.tag or "")
    local max_results = math.max(1, math.min(tonumber(args.max_results) or 200, 1000))

    local results = {}
    local total_matching = 0

    for _, obj in ipairs(getObjects()) do
        local object_name = string.lower(tostring(obj.getName() or ""))
        local name_matches = name_filter == "" or string.find(
            object_name,
            name_filter,
            1,
            true
        ) ~= nil

        if name_matches and mcp_has_tag(obj, tag_filter) then
            total_matching = total_matching + 1
            if #results < max_results then
                table.insert(results, args.compact == true and mcp_compact_object_summary(obj) or mcp_object_summary(obj))
            end
        end
    end

    return {
        count = #results,
        total_matching = total_matching,
        truncated = total_matching > #results,
        objects = results,
    }
end

MCP_HANDLERS.find_nearest_objects = function(args, request_id)
    local origin = args.position
    if type(origin) ~= "table" and args.guid ~= nil then
        origin = mcp_require_object(args.guid).getPosition()
    end
    if type(origin) ~= "table" then
        error("position or guid is required.")
    end

    local max_results = math.max(1, math.min(tonumber(args.max_results) or 10, 100))
    local candidates = {}
    for _, obj in ipairs(getObjects()) do
        if (args.include_self == true or args.guid == nil or obj.getGUID() ~= args.guid)
            and mcp_matches_filters(obj, args) then
            local position = obj.getPosition()
            table.insert(candidates, {
                distance = math.sqrt(mcp_distance_squared(origin, position)),
                object = obj,
            })
        end
    end

    table.sort(candidates, function(a, b) return a.distance < b.distance end)
    local results = {}
    for index, candidate in ipairs(candidates) do
        if index > max_results then
            break
        end
        local summary = mcp_object_summary(candidate.object)
        summary.distance = candidate.distance
        table.insert(results, summary)
    end
    return {
        origin = mcp_vector(origin),
        count = #results,
        total_matching = #candidates,
        truncated = #candidates > #results,
        objects = results,
    }
end

MCP_HANDLERS.find_objects_in_region = function(args, request_id)
    local minimum = args.minimum
    local maximum = args.maximum
    if type(minimum) ~= "table" or type(maximum) ~= "table" then
        error("minimum and maximum world-coordinate vectors are required.")
    end
    minimum = {
        x = math.min(tonumber(minimum.x) or 0, tonumber(maximum.x) or 0),
        y = math.min(tonumber(minimum.y) or 0, tonumber(maximum.y) or 0),
        z = math.min(tonumber(minimum.z) or 0, tonumber(maximum.z) or 0),
    }
    maximum = {
        x = math.max(tonumber(minimum.x) or 0, tonumber(maximum.x) or 0),
        y = math.max(tonumber(minimum.y) or 0, tonumber(maximum.y) or 0),
        z = math.max(tonumber(minimum.z) or 0, tonumber(maximum.z) or 0),
    }

    local max_results = math.max(1, math.min(tonumber(args.max_results) or 200, 1000))
    local results = {}
    local total_matching = 0
    for _, obj in ipairs(getObjects()) do
        if mcp_matches_filters(obj, args) and mcp_region_contains_object(obj, minimum, maximum) then
            total_matching = total_matching + 1
            if #results < max_results then
                table.insert(results, mcp_object_summary(obj))
            end
        end
    end
    return {
        minimum = minimum,
        maximum = maximum,
        count = #results,
        total_matching = total_matching,
        truncated = total_matching > #results,
        objects = results,
    }
end

MCP_HANDLERS.measure_distance = function(args, request_id)
    local first = mcp_position_from_args(args, "first")
    local second = mcp_position_from_args(args, "second")
    return {
        first = mcp_vector(first),
        second = mcp_vector(second),
        distance = math.sqrt(mcp_distance_squared(first, second)),
    }
end

MCP_HANDLERS.relative_transform = function(args, request_id)
    local from_obj = mcp_require_object(args.from_guid)
    local to_obj = mcp_require_object(args.to_guid)
    local from_position = from_obj.getPosition()
    local to_position = to_obj.getPosition()
    local from_rotation = from_obj.getRotation()
    local to_rotation = to_obj.getRotation()
    return {
        from_guid = args.from_guid,
        to_guid = args.to_guid,
        from_position = mcp_vector(from_position),
        to_position = mcp_vector(to_position),
        position_delta = {
            x = to_position.x - from_position.x,
            y = to_position.y - from_position.y,
            z = to_position.z - from_position.z,
        },
        rotation_delta = {
            x = to_rotation.x - from_rotation.x,
            y = to_rotation.y - from_rotation.y,
            z = to_rotation.z - from_rotation.z,
        },
        distance = math.sqrt(mcp_distance_squared(from_position, to_position)),
    }
end

MCP_HANDLERS.inspect_container = function(args, request_id)
    local container = mcp_require_object(args.guid)
    local items = mcp_container_items(container)
    if items == nil then
        error("Object " .. args.guid .. " is not a supported container.")
    end
    return {
        container = mcp_object_summary(container),
        contents = items,
    }
end

MCP_HANDLERS.get_zone_objects = function(args, request_id)
    local zone = mcp_require_object(args.guid)
    local objects = mcp_try(function()
        return zone.getObjects(args.ignore_tags == true)
    end)
    if type(objects) ~= "table" then
        error("Object " .. args.guid .. " is not a zone.")
    end
    local results = {}
    for _, object in ipairs(objects) do
        table.insert(results, mcp_object_summary(object))
    end
    return {
        zone = mcp_object_summary(zone),
        count = #results,
        objects = results,
    }
end

MCP_HANDLERS.get_snap_points = function(args, request_id)
    local object = mcp_require_object(args.guid)
    local points = mcp_try(function() return object.getSnapPoints() end)
    if type(points) ~= "table" then
        error("Object " .. args.guid .. " does not expose snap points.")
    end
    return {
        guid = args.guid,
        count = #points,
        snap_points = points,
    }
end

MCP_HANDLERS.take_from_container = function(args, request_id)
    local container = mcp_require_object(args.container_guid)
    local parameters = {
        position = args.position or container.getPosition(),
        rotation = args.rotation,
        flip = args.flip == true,
        smooth = args.smooth ~= false,
        callback_function = function(taken)
            mcp_send_ok(request_id, {
                container_guid = args.container_guid,
                object = mcp_object_summary(taken),
            })
        end,
    }
    if args.index ~= nil then
        parameters.index = tonumber(args.index)
    elseif args.item_guid ~= nil then
        parameters.guid = tostring(args.item_guid)
    else
        error("index or item_guid is required.")
    end
    local taken = container.takeObject(parameters)
    if taken == nil then
        error("takeObject returned nil")
    end
    return nil, true
end

-- V6-compatible catalog spawning.  The Python side supplies the catalog GUID
-- plus container path metadata; this handler temporarily extracts the source
-- object, clones it at the requested position, and returns the source to its
-- bag.  No arbitrary Lua or catalog lookup is exposed to the caller.
local function mcp_find_named_object(name)
    local wanted = string.lower(tostring(name or ""))
    if wanted == "" then return nil end
    for _, candidate in ipairs(getObjects()) do
        if string.lower(tostring(candidate.getName() or "")) == wanted then
            return candidate
        end
    end
    return nil
end

local function mcp_catalog_clone(source, args, request_id, parent, cleanup)
    if source == nil or source.isDestroyed() then error("Catalog source container is unavailable") end
    local position = args.position or {x = 0, y = 2, z = 0}
    local function clone_source(object)
        if object == nil or object.isDestroyed() then error("Catalog object was not taken from its container") end
        local clone = object.clone({position = position})
        if clone == nil then error("Could not clone catalog object " .. tostring(args.guid)) end
        Wait.frames(function()
            if cleanup and parent and not parent.isDestroyed() and not source.isDestroyed() then
                source.putObject(object)
            elseif not source.isDestroyed() then
                source.putObject(object)
            end
            mcp_send_ok(request_id, {
                action = "spawn_catalog",
                guid = args.guid,
                object = mcp_object_summary(clone),
            })
        end, 2)
    end
    source.takeObject({
        guid = tostring(args.guid),
        position = {x = position.x, y = position.y + 3, z = position.z},
        smooth = false,
        callback_function = clone_source,
    })
end

MCP_HANDLERS.spawn_catalog = function(args, request_id)
    local guid = tostring(args.guid or "")
    if not string.match(guid, "^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
        error("A valid six-character catalog GUID is required")
    end
    args.position = args.position or {x = tonumber(args.x) or 0, y = tonumber(args.y) or 2, z = tonumber(args.z) or 0}

    -- Preserve V6 behavior when the source is already on the table: clone it.
    local existing = getObjectFromGUID(guid)
    if existing and existing.type ~= "Bag" and existing.type ~= "Infinite_Bag" then
        local clone = existing.clone({position = args.position})
        if not clone then error("Could not clone catalog object " .. guid) end
        return {action = "spawn_catalog", guid = guid, object = mcp_object_summary(clone)}
    end

    local path = args.container_path
    local container = nil
    if args.container_guid and tostring(args.container_guid) ~= "" then
        container = getObjectFromGUID(tostring(args.container_guid))
    elseif type(path) == "table" and #path > 0 then
        if args.master_bag_guid and tostring(args.master_bag_guid) ~= "" then
            container = getObjectFromGUID(tostring(args.master_bag_guid))
        end
        container = container or mcp_find_named_object(path[1])
        -- V6 catalogs commonly use [master bag, category bag]. Extract the
        -- category bag temporarily before taking the requested object.
        if container and #path >= 2 then
            local target_name = tostring(path[#path])
            local contents = container.getObjects()
            local target_guid = nil
            for _, item in ipairs(contents or {}) do
                if string.lower(tostring(item.name or "")) == string.lower(target_name) then
                    target_guid = item.guid
                    break
                end
            end
            if target_guid then
                container.takeObject({guid = target_guid, position = {x = 0, y = 8, z = 0}, smooth = false,
                    callback_function = function(category)
                        Wait.frames(function() mcp_catalog_clone(category, args, request_id, container, true) end, 5)
                        Wait.frames(function() if category and not category.isDestroyed() and container and not container.isDestroyed() then container.putObject(category) end end, 20)
                    end})
                return nil, true
            end
        end
    elseif args.container_name then
        container = mcp_find_named_object(args.container_name)
    end
    if not container then error("Could not locate the catalog container for " .. guid) end
    mcp_catalog_clone(container, args, request_id, nil, false)
    return nil, true
end

MCP_HANDLERS.place_catalog = function(args, request_id)
    local guid = tostring(args.guid or "")
    local object = getObjectFromGUID(guid)
    if object then
        object.setPositionSmooth(args.position or {x = args.x or 0, y = args.y or 2, z = args.z or 0}, false, true)
        return {action = "place_catalog", guid = guid, object = mcp_object_summary(object)}
    end
    return MCP_HANDLERS.spawn_catalog(args, request_id)
end

MCP_HANDLERS.put_object_into_container = function(args, request_id)
    local container = mcp_require_object(args.container_guid)
    local object = mcp_require_object(args.object_guid)
    local result = container.putObject(object, args.index)
    return {
        container = mcp_object_summary(result or container),
        object_guid = args.object_guid,
        container_guid = args.container_guid,
    }
end

MCP_HANDLERS.get_object = function(args, request_id)
    return mcp_compact_object_summary(mcp_require_object(args.guid))
end

MCP_HANDLERS.set_camera = function(args, request_id)
    local player_color = tostring(args.player_color or "White")
    local player = Player[player_color]
    if player == nil then
        error("Invalid player color: " .. player_color)
    end

    local requested = args.position or {}
    local position = {
        x = tonumber(requested.x or requested[1]) or 0,
        y = tonumber(requested.y or requested[2]) or 0,
        z = tonumber(requested.z or requested[3]) or 0,
    }
    local mode = tostring(args.mode or "ThirdPerson")
    if mode ~= "ThirdPerson" and mode ~= "FirstPerson" and mode ~= "TopDown" then
        error("Invalid camera mode: " .. mode)
    end

    player.lookAt({
        position = position,
        pitch = tonumber(args.pitch) or 45,
        yaw = tonumber(args.yaw) or 180,
        distance = tonumber(args.distance) or 30,
    })
    -- lookAt forces ThirdPerson, so apply the requested mode afterward.
    player.setCameraMode(mode)

    return {
        player_color = player_color,
        mode = mode,
        position = position,
        pitch = tonumber(args.pitch) or 45,
        yaw = tonumber(args.yaw) or 180,
        distance = tonumber(args.distance) or 30,
    }
end

MCP_HANDLERS.move_object = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    local requested = args.position

    if type(requested) ~= "table" then
        error("position must be a table containing x, y, and z.")
    end

    -- Build a fresh Lua table from the decoded values. Do not pass the
    -- External Editor's managed table directly to TTS object APIs.
    local x = tonumber(requested.x or requested[1])
    local y = tonumber(requested.y or requested[2])
    local z = tonumber(requested.z or requested[3])
    if x == nil or y == nil or z == nil then
        error("position must contain numeric x, y, and z values.")
    end
    local position = {x = x, y = y, z = z}

    -- This deliberately matches the V6 movement path: resolve the in-scene
    -- GUID first, then pass a native Lua position table to TTS.  Do not pass
    -- any External Editor-provided vector/table to setPositionSmooth.
    obj.setPositionSmooth(position, false, false)

    -- setPositionSmooth is asynchronous.  Reply after the move has had a
    -- short opportunity to settle so Python's post-command get_object check
    -- observes the real TTS position instead of the old transform.
    local guid = obj.getGUID()
    Wait.frames(function()
        local moved = getObjectFromGUID(guid)
        local actual = moved and moved.getPosition() or position
        mcp_send_ok(request_id, {
            action = "move_object",
            guid = guid,
            position = {
                x = tonumber(actual.x) or x,
                y = tonumber(actual.y) or y,
                z = tonumber(actual.z) or z,
            },
        })
    end, 20)
    return nil, true
end

MCP_HANDLERS.rotate_object = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    local rotation = args.rotation

    if type(rotation) ~= "table" then
        error("rotation must be a table containing x, y, and z.")
    end

    if args.smooth == false then
        obj.setRotation(rotation)
    else
        obj.setRotationSmooth(
            rotation,
            args.collide == true,
            args.fast ~= false
        )
    end
    return mcp_object_summary(obj)
end

MCP_HANDLERS.set_object_name = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    obj.setName(tostring(args.name or ""))
    return mcp_object_summary(obj)
end

MCP_HANDLERS.set_object_lock = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    obj.setLock(args.locked == true)
    return mcp_object_summary(obj)
end

MCP_HANDLERS.spawn_builtin = function(args, request_id)
    local object_type = tostring(args.object_type or "")
    if object_type == "" then
        error("object_type is required.")
    end

    local params = {
        type = object_type,
        position = args.position or {x = 0, y = 3, z = 0},
        rotation = args.rotation or {x = 0, y = 0, z = 0},
        scale = args.scale or {x = 1, y = 1, z = 1},
        sound = false,
        snap_to_grid = false,
        callback_function = function(spawned)
            if args.name ~= nil and tostring(args.name) ~= "" then
                spawned.setName(tostring(args.name))
            end
            spawned.setLock(args.locked == true)
            mcp_send_ok(request_id, mcp_object_summary(spawned))
        end,
    }

    local spawned = spawnObject(params)
    if spawned == nil then
        error("spawnObject returned nil for type " .. object_type)
    end

    -- The callback sends the response after TTS finishes spawning the object.
    return nil, true
end

MCP_HANDLERS.destroy_object = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    local previous = mcp_object_summary(obj)
    destroyObject(obj)
    return {
        destroyed = true,
        previous = previous,
    }
end

MCP_HANDLERS.broadcast = function(args, request_id)
    local message = tostring(args.message or "")
    broadcastToAll(message, {r = 1, g = 1, b = 1})
    return {broadcast = true, message = message}
end

local function mcp_forward_chat(message, sender)
    local event = {
        channel = MCP_CHANNEL,
        event = "chat_message",
        message = tostring(message or ""),
        player_color = sender and tostring(sender.color or "") or "",
        player_name = sender and tostring(sender.steam_name or sender.name or "") or "",
    }
    -- Send an unsolicited External Editor event. Do not use print(), because
    -- that creates a visible [tts-mcp-chat] line in the TTS console/chat.
    Wait.frames(function()
        sendExternalMessage(event)
    end, 1)
end

function mcp_handleExternalMessage(data)
    -- TTS normally passes the messageID=2 customMessage table directly to
    -- onExternalMessage.  Some External Editor-compatible hosts pass the
    -- complete envelope instead, so unwrap that form as well.  Supporting
    -- both forms keeps the bridge from silently ignoring commands and
    -- leaving the Python caller waiting for a response.
    if type(data) == "table" and data.messageID == 2 then
        data = data.customMessage
    end
    -- TTS can pass custom messages directly as a JSON string, rather than in
    -- the messageID=2 envelope. Decode either delivery form before routing.
    if type(data) == "string" then
        local ok, decoded = pcall(function() return JSON.decode(data) end)
        if not ok then
            return false
        end
        data = decoded
    end

    if type(data) ~= "table" or data.channel ~= MCP_CHANNEL then
        return false
    end

    local request_id = tostring(data.requestId or "")
    local action = tostring(data.action or "")

    -- Movement is scalar-only at the External Editor boundary.  Rebuild the
    -- argument and position tables here instead of reading the nested args
    -- wrapper that causes MoonSharp's "Specified cast is not valid" error.
    if action == "move_object" then
        local move_args = {
            guid = tostring(data.guid or ""),
            position = {
                x = tonumber(data.x),
                y = tonumber(data.y),
                z = tonumber(data.z),
            },
        }
        local handler = MCP_HANDLERS[action]
        print("[tts-mcp] received action: " .. action)
        if handler == nil then
            mcp_send_error(request_id, "Unknown MCP action: " .. action)
            return true
        end
        local ok, result, deferred = pcall(handler, move_args, request_id)
        if not ok then
            mcp_send_error(request_id, result)
        elseif deferred ~= true then
            mcp_send_ok(request_id, result)
        end
        return true
    end

    local args = data.args or {}
    -- Object-form External Editor messages can lose values nested under args.
    -- Python mirrors these action fields at the message root for this narrow
    -- compatibility fallback.
    if args.guid == nil and data.guid ~= nil then args.guid = data.guid end
    if args.position == nil and data.position ~= nil then args.position = data.position end
    if args.rotation == nil and data.rotation ~= nil then args.rotation = data.rotation end
    if args.locked == nil and data.locked ~= nil then args.locked = data.locked end
    local handler = MCP_HANDLERS[action]

    print("[tts-mcp] received action: " .. action)

    if handler == nil then
        mcp_send_error(request_id, "Unknown MCP action: " .. action)
        return true
    end

    local ok, result, deferred = pcall(handler, args, request_id)
    if not ok then
        mcp_send_error(request_id, result)
    elseif deferred ~= true then
        mcp_send_ok(request_id, result)
    end
    return true
end

-- Remove this wrapper if the mod already has onExternalMessage(data). In that
-- case, call mcp_handleExternalMessage(data) from the existing handler.
function onExternalMessage(data)
    mcp_handleExternalMessage(data)
end

-- Forward player chat to MCP as an unsolicited custom event.
-- If the mod already defines onChat, call mcp_forward_chat(message, sender)
-- from that existing handler instead of defining a second onChat function.
function onChat(message, sender)
    mcp_forward_chat(message, sender)

    local raw_message = tostring(message or "")
    WebRequest.custom(
        MCP_HTTP_CHAT_URL,
        "POST",
        true,
        JSON.encode({
            message = raw_message,
            player = {
                color = sender and tostring(sender.color or "") or "",
                steam_name = sender and tostring(sender.steam_name or "") or "",
                steam_id = sender and tostring(sender.steam_id or "") or "",
                host = sender and sender.host == true or false,
            },
        }),
        { ["Content-Type"] = "application/json", ["Accept"] = "application/json" },
        function(request)
            if request.is_error then
                printToAll("[TTS AI] HTTP error: " .. tostring(request.error), {1, 0.4, 0.4})
                return
            end
            if request.response_code < 200 or request.response_code >= 300 then
                printToAll("[TTS AI] HTTP status: " .. tostring(request.response_code), {1, 0.4, 0.4})
                return
            end

            local ok, response = pcall(function() return JSON.decode(request.text or "") end)
            if not ok or type(response) ~= "table" then
                printToAll("[TTS AI] Invalid JSON response", {1, 0.4, 0.4})
                return
            end
            local text = tostring(response.text or "")
            if text ~= "" then
                printToAll(text, {0.65, 0.9, 1.0})
            end
        end
    )
    return true
end
