-- Tabletop Simulator MCP bridge
-- Install this in the loaded game's Global script.
--
-- If the mod already defines onExternalMessage(data), do not keep the wrapper
-- at the bottom of this file. Instead, call:
--     mcp_handleExternalMessage(data)
-- from the mod's existing onExternalMessage function.

local MCP_CHANNEL = "tts-mcp"
local MCP_HTTP_CHAT_URL = "http://127.0.0.1:8765/chat"
-- A private callback for bridge results. Unlike print(), this never appears
-- in the in-game player chat or console feed.
local MCP_HTTP_BRIDGE_RESPONSE_URL = "http://127.0.0.1:8765/bridge/response"
-- Diagnostics belong in the Python server trace, not in player chat or the
-- normal TTS output. Enable only for Lua-side troubleshooting.
local MCP_DEBUG_PRINT = false
local function mcp_debug(message)
    if MCP_DEBUG_PRINT then
        print(message)
    end
end
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

-- External Editor callbacks are size-sensitive. AI scene inspection needs
-- identity, transforms, bounds, and the small motion signal used by settle
-- polling; omit the larger volatile velocity/axis metadata.
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
        smooth_moving = mcp_try(function() return obj.isSmoothMoving() end),
        smooth_position = mcp_vector(mcp_try(function() return obj.getPositionSmooth() end)),
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

local function mcp_post_bridge_response(response)
    -- Keep a second, non-player-visible response path for TTS builds that
    -- drop sendExternalMessage callbacks. The Python gateway correlates the
    -- requestId with its pending bridge request.
    WebRequest.custom(
        MCP_HTTP_BRIDGE_RESPONSE_URL,
        "POST",
        true,
        JSON.encode(response),
        { ["Content-Type"] = "application/json", ["Accept"] = "application/json" },
        function(request)
            if request.is_error then
                mcp_debug("[tts-mcp] HTTP response callback failed: " .. tostring(request.error))
            elseif request.response_code < 200 or request.response_code >= 300 then
                mcp_debug("[tts-mcp] HTTP response callback status: " .. tostring(request.response_code))
            end
        end
    )
end

local function mcp_send_ok(request_id, result)
    mcp_debug("[tts-mcp] sending success response for " .. tostring(request_id))
    local response = {
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = true,
        result = mcp_json_safe(result),
    }
    -- Send once immediately and once after the callback returns. Different
    -- TTS builds have dropped one of these timing modes, while the Python
    -- request waiter safely ignores a duplicate response.
    mcp_post_bridge_response(response)
    sendExternalMessage(response)
    Wait.frames(function()
        sendExternalMessage(response)
        mcp_debug("[tts-mcp] success response sent")
    end, 1)
end

local function mcp_send_error(request_id, err)
    mcp_debug("[tts-mcp] sending error response for " .. tostring(request_id))
    local response = {
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = false,
        error = tostring(err),
    }
    mcp_post_bridge_response(response)
    sendExternalMessage(response)
    Wait.frames(function()
        sendExternalMessage(response)
        mcp_debug("[tts-mcp] error response sent")
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

    -- Resolve the in-scene GUID first, then pass a native Lua position table
    -- to TTS. Do not pass any External Editor-provided vector/table to the
    -- object API. The generic tool remains unrestricted, so honor its motion
    -- options here rather than silently forcing smooth movement.
    if args.smooth == false then
        obj.setPosition(position)
    else
        obj.setPositionSmooth(position, args.collide == true, args.fast ~= false)
    end

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

local function mcp_trim(value)
    -- Avoid Lua patterns for whole AI responses. MoonSharp can report
    -- "pattern too complex" when a non-greedy trim pattern scans a large
    -- multimodal response.
    local text = tostring(value or "")
    local first = 1
    local last = string.len(text)
    while first <= last do
        local char = string.sub(text, first, first)
        if char ~= " " and char ~= "\t" and char ~= "\r" and char ~= "\n" then
            break
        end
        first = first + 1
    end
    while last >= first do
        local char = string.sub(text, last, last)
        if char ~= " " and char ~= "\t" and char ~= "\r" and char ~= "\n" then
            break
        end
        last = last - 1
    end
    if first > last then
        return ""
    end
    return string.sub(text, first, last)
end

local function mcp_split_lines(text)
    local lines = {}
    local start_index = 1
    local length = string.len(text)
    for index = 1, length do
        if string.sub(text, index, index) == "\n" then
            table.insert(lines, string.sub(text, start_index, index - 1))
            start_index = index + 1
        end
    end
    table.insert(lines, string.sub(text, start_index, length))
    return lines
end

local function mcp_collapse_horizontal_whitespace(value)
    local text = tostring(value or "")
    local chars = {}
    local pending_space = false
    for index = 1, string.len(text) do
        local char = string.sub(text, index, index)
        if char == " " or char == "\t" then
            pending_space = true
        else
            if pending_space and #chars > 0 then
                table.insert(chars, " ")
            end
            table.insert(chars, char)
            pending_space = false
        end
    end
    return table.concat(chars)
end

local function mcp_public_chat_text(value)
    -- Final player-chat boundary: internal board snapshots and telemetry must
    -- never be broadcast, even if an older Python gateway returns them.
    local text = tostring(value or "")
    text = mcp_trim(text)
    if text == "" then
        return ""
    end
    -- JSON is transport data, not player-facing chat. This also catches
    -- multi-line JSON responses before row-level filtering below.
    local json_ok, decoded = pcall(function() return JSON.decode(text) end)
    if json_ok and type(decoded) == "table" then
        return ""
    end
    local lines = {}
    for _, raw_line in ipairs(mcp_split_lines(text)) do
        local line = mcp_trim(raw_line)
        -- TTS renders tabs and repeated spaces literally; keep the final
        -- player-facing message compact even if the backend padded a line.
        line = mcp_collapse_horizontal_whitespace(line)
        if line ~= "" then
            local lowered = string.lower(line)
            local has_guid = string.find(lowered, "guid", 1, true) ~= nil
            local has_position = string.find(lowered, "position", 1, true) ~= nil
            local has_rotation = string.find(lowered, "rotation", 1, true) ~= nil
            local has_bounds = string.find(lowered, "bounds", 1, true) ~= nil
            local is_internal_header = string.find(lowered, "current tabletop simulator state", 1, true) ~= nil
                or string.find(lowered, "relevant scene/catalog candidates", 1, true) ~= nil
                or string.find(lowered, "authoritative current context", 1, true) ~= nil
            local is_raw_state = (has_guid and (has_position or has_rotation or has_bounds))
                or (string.sub(line, 1, 1) == "{" and string.sub(line, -1) == "}")
            if not is_internal_header and not is_raw_state then
                table.insert(lines, line)
            end
        end
    end
    text = table.concat(lines, "\n")
    text = mcp_trim(text)
    if string.len(text) > 2000 then
        text = string.sub(text, 1, 1997) .. "..."
    end
    return text
end

local function mcp_decode_message(data)
    if type(data) ~= "string" then
        return data
    end
    local ok, decoded = pcall(function() return JSON.decode(data) end)
    if not ok then
        return nil
    end
    return decoded
end

local function mcp_unwrap_external_message(data)
    -- TTS can deliver either a Lua table or a JSON string. Decode first, then
    -- unwrap the messageID=2 envelope; doing this in the opposite order drops
    -- commands when the decoded envelope still contains messageID=2.
    data = mcp_decode_message(data)
    if type(data) == "table" and tostring(data.messageID or "") == "2" then
        data = mcp_decode_message(data.customMessage)
    end
    return data
end

function mcp_handleExternalMessage(data)
    data = mcp_unwrap_external_message(data)

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
            smooth = data.smooth ~= false,
            collide = data.collide == true,
            fast = data.fast ~= false,
        }
        local handler = MCP_HANDLERS[action]
        mcp_debug("[tts-mcp] received action: " .. action)
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

    mcp_debug("[tts-mcp] received action: " .. action)

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
    raw_message = mcp_trim(raw_message)
    if raw_message == "" then
        mcp_debug("[TTS AI] chat ignored: empty message")
        return nil
    end
    mcp_debug("[TTS AI] chat received; sending to http://127.0.0.1:8765/chat")
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
                mcp_debug("[TTS AI] HTTP error: " .. tostring(request.error))
                return
            end
            mcp_debug("[TTS AI] HTTP response: " .. tostring(request.response_code))
            if request.response_code < 200 or request.response_code >= 300 then
                local body = tostring(request.text or "")
                if string.len(body) > 500 then
                    body = string.sub(body, 1, 497) .. "..."
                end
                mcp_debug("[TTS AI] HTTP status: " .. tostring(request.response_code) .. " body: " .. body)
                return
            end

            local ok, response = pcall(function() return JSON.decode(request.text or "") end)
            if not ok or type(response) ~= "table" then
                mcp_debug("[TTS AI] Invalid JSON response")
                return
            end
            local text = mcp_public_chat_text(response.text or "")
            if text ~= "" then
                -- Explicit alpha avoids TTS's translucent default text.
                printToAll(text, {r = 1, g = 1, b = 1, a = 1})
            end
        end
    )
    -- Do not consume the original player message. Returning nil preserves
    -- TTS's normal chat rendering while the AI reply is handled separately.
    return nil
end
