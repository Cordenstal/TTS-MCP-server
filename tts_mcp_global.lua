-- Tabletop Simulator MCP bridge
-- Install this in the loaded game's Global script.
--
-- If the mod already defines onExternalMessage(data), do not keep the wrapper
-- at the bottom of this file. Instead, call:
--     mcp_handleExternalMessage(data)
-- from the mod's existing onExternalMessage function.

local MCP_CHANNEL = "tts-mcp"
-- Change this whenever the installed Global bridge has a behavior change.
-- `tts_ping` returns it so a live TTS table can be distinguished from the
-- source file on disk when the External Editor reports only guid=-1.
local MCP_BRIDGE_VERSION = "2026-07-29-generic-killteam-move-v18"
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
    return { x = v.x, y = v.y, z = v.z }
end

local function mcp_try(fn)
    local ok, value = pcall(fn)
    if ok then
        return value
    end
    return nil
end

local function mcp_decode_json_array(value, label)
    -- Scalar values inside object-form External Editor messages can be
    -- managed MoonSharp strings. Coerce them before invoking TTS's JSON
    -- decoder so the decoder receives an ordinary Lua string.
    local text = mcp_try(function() return tostring(value or "[]") end)
    if type(text) ~= "string" then
        error(tostring(label) .. " is not a readable JSON string")
    end
    local ok, decoded = pcall(function() return JSON.decode(text) end)
    if not ok or type(decoded) ~= "table" then
        error(tostring(label) .. " must decode to an array")
    end
    return decoded
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

local function mcp_die_value(obj)
    if obj == nil then
        return nil
    end
    local value = mcp_try(function() return obj.getRotationValue() end)
    if value == nil then
        value = mcp_try(function() return obj.getValue() end)
    end
    return tonumber(value)
end

local function mcp_counter_value(obj)
    if obj == nil then
        return nil
    end
    local counter = mcp_try(function() return obj.Counter end)
    if counter == nil then
        return nil
    end
    return tonumber(mcp_try(function() return counter.getValue() end))
end

local function mcp_container_items(obj)
    local object_type = tostring(mcp_try(function() return obj.type end) or "")
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
        die_value = mcp_die_value(obj),
        counter_value = mcp_counter_value(obj),
    }
end

-- External Editor callbacks are size-sensitive. AI scene inspection needs
-- identity, transforms, bounds, and the small motion signal used by settle
-- polling; omit the larger volatile velocity/axis metadata.
local function mcp_compact_object_summary(obj)
    return {
        guid = mcp_try(function() return obj.getGUID() end),
        name = mcp_try(function() return obj.getName() end),
        description = mcp_try(function() return obj.getDescription() end),
        type = mcp_try(function() return obj.type end) or mcp_try(function() return obj.tag end),
        tags = mcp_try(function() return obj.getTags() end) or {},
        position = mcp_vector(mcp_try(function() return obj.getPosition() end)),
        rotation = mcp_vector(mcp_try(function() return obj.getRotation() end)),
        bounds = mcp_bounds(mcp_try(function() return obj.getBounds() end)),
        locked = mcp_try(function() return obj.getLock() end),
        smooth_moving = mcp_try(function() return obj.isSmoothMoving() end),
        smooth_position = mcp_vector(mcp_try(function() return obj.getPositionSmooth() end)),
        zone_guids = mcp_zone_guids(obj),
        die_value = mcp_die_value(obj),
        counter_value = mcp_counter_value(obj),
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
            return { x = tonumber(x) or 0, y = tonumber(y) or 0, z = tonumber(z) or 0 }
        end
        return tostring(value)
    end
    if value_type == "table" then
        local safe = {}
        -- A TTS-managed table can become invalid while a model or container
        -- is unloading. Keep serialization from escaping the dispatch pcall;
        -- the caller still receives a correlated response with a bounded
        -- placeholder instead of an External Editor timeout.
        local encoded_ok = pcall(function()
            for key, item in pairs(value) do
                local key_type = type(key)
                if key_type == "string" or key_type == "number" then
                    safe[key] = mcp_json_safe(item, depth + 1)
                end
            end
        end)
        if not encoded_ok then
            return "<unreadable>"
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

local function mcp_send_bridge_response(response)
    -- The optional HTTP fallback must never prevent the native External
    -- Editor response. In particular, WebRequest.custom can throw before it
    -- queues a request when TTS rejects a local endpoint or its web subsystem
    -- is unavailable. Keep each transport isolated so one failed path cannot
    -- turn a valid command into a Python-side timeout.
    local posted, post_err = pcall(mcp_post_bridge_response, response)
    if not posted then
        mcp_debug("[tts-mcp] HTTP response callback could not start: " .. tostring(post_err))
    end

    local sent, send_err = pcall(sendExternalMessage, response)
    if not sent then
        mcp_debug("[tts-mcp] External Editor response failed: " .. tostring(send_err))
    end

    -- Retain the next-frame retry for TTS builds that drop an immediate
    -- External Editor callback, while isolating it from any callback error.
    -- The bundled roller waits 0.3 seconds, then waits another 35 frames
    -- before assigning die values. Sampling after 30 frames reads the dice
    -- before that callback has settled and can return an empty face list.
    Wait.frames(function()
        local retried, retry_err = pcall(sendExternalMessage, response)
        if not retried then
            mcp_debug("[tts-mcp] External Editor retry failed: " .. tostring(retry_err))
        end
    end, 1)
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
    mcp_send_bridge_response(response)
    mcp_debug("[tts-mcp] success response queued")
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
    mcp_send_bridge_response(response)
    mcp_debug("[tts-mcp] error response queued")
end

local function mcp_require_object(guid)
    if type(guid) ~= "string" or guid == "" then
        error("A non-empty object GUID is required.")
    end

    local obj = getObjectFromGUID(guid)
    if obj == nil then
        error("No in-scene object exists with GUID " .. guid)
    end
    local actual_guid = mcp_try(function() return obj.getGUID() end)
    if actual_guid == nil or tostring(actual_guid) == "" or tostring(actual_guid) == "-1" then
        error("Object " .. guid .. " is no longer a valid in-scene object")
    end
    return obj
end

local function mcp_safe_object_tags(obj)
    local tags = mcp_try(function() return obj.getTags() end)
    return type(tags) == "table" and tags or {}
end

local function mcp_has_tag(obj, requested)
    if requested == nil or requested == "" then
        return true
    end

    local wanted = string.lower(tostring(requested))
    local tags = mcp_safe_object_tags(obj)
    for _, actual in ipairs(tags) do
        if string.lower(tostring(actual)) == wanted then
            return true
        end
    end
    return false
end

local function mcp_live_object(obj)
    if obj == nil then
        return false
    end
    local guid = mcp_try(function() return obj.getGUID() end)
    -- TTS can briefly leave stale object references in getObjects() while a
    -- model is being destroyed, unloaded, or moved between containers. Those
    -- references commonly report GUID -1 and must not abort an entire list.
    return guid ~= nil and tostring(guid) ~= "" and tostring(guid) ~= "-1"
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
    local size = { x = 0, y = 0, z = 0 }
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
    local object_count = mcp_try(function() return #getObjects() end)
    return {
        bridge = MCP_CHANNEL,
        bridge_version = MCP_BRIDGE_VERSION,
        object_count = tonumber(object_count) or -1,
        message = "Tabletop Simulator MCP bridge is active.",
    }
end

MCP_HANDLERS.list_objects = function(args, request_id)
    local name_filter = string.lower(tostring(args.name_contains or ""))
    local tag_filter = tostring(args.tag or "")
    local max_results = math.max(1, math.min(tonumber(args.max_results) or 200, 1000))

    local results = {}
    local total_matching = 0
    local skipped_invalid = 0

    -- Keep scene enumeration itself correlated. Individual stale references
    -- are filtered below, but a failed getObjects() call must not leave the
    -- MCP client waiting for a response that TTS will never send.
    local objects_ok, objects_or_error = pcall(getObjects)
    if not objects_ok then
        error("TTS scene enumeration failed: " .. tostring(objects_or_error))
    end
    if type(objects_or_error) ~= "table" then
        error("TTS scene enumeration returned an invalid object list")
    end

    for _, obj in ipairs(objects_or_error) do
        local live_ok, live = pcall(mcp_live_object, obj)
        if not live_ok or not live then
            skipped_invalid = skipped_invalid + 1
        else
            local object_name = string.lower(tostring(mcp_try(function() return obj.getName() end) or ""))
            local name_matches = name_filter == "" or string.find(
                object_name,
                name_filter,
                1,
                true
            ) ~= nil

            if name_matches and mcp_has_tag(obj, tag_filter) then
                local summary_ok, summary = pcall(function()
                    return args.compact == true and mcp_compact_object_summary(obj) or mcp_object_summary(obj)
                end)
                if summary_ok and type(summary) == "table" and mcp_live_object(obj) and summary.guid ~= nil then
                    total_matching = total_matching + 1
                    if #results < max_results then
                        table.insert(results, summary)
                    end
                end
            end
        end
    end

    return {
        count = #results,
        total_matching = total_matching,
        skipped_invalid = skipped_invalid,
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
    local normalized_points = {}
    for _, point in ipairs(points) do
        local normalized = {
            position = point.position,
            rotation = point.rotation,
            tags = point.tags,
        }
        local world_position = mcp_try(function()
            return object.positionToWorld(point.position)
        end)
        if type(world_position) == "table" then
            normalized.world_position = {
                x = tonumber(world_position.x) or 0,
                y = tonumber(world_position.y) or 0,
                z = tonumber(world_position.z) or 0,
            }
        end
        table.insert(normalized_points, normalized)
    end
    return {
        guid = args.guid,
        count = #normalized_points,
        snap_points = normalized_points,
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
    local position = args.position or { x = 0, y = 2, z = 0 }
    local function clone_source(object)
        if object == nil or object.isDestroyed() then error("Catalog object was not taken from its container") end
        local clone = object.clone({ position = position })
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
        position = { x = position.x, y = position.y + 3, z = position.z },
        smooth = false,
        callback_function = clone_source,
    })
end

MCP_HANDLERS.spawn_catalog = function(args, request_id)
    local guid = tostring(args.guid or "")
    if not string.match(guid, "^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
        error("A valid six-character catalog GUID is required")
    end
    args.position = args.position or { x = tonumber(args.x) or 0, y = tonumber(args.y) or 2, z = tonumber(args.z) or 0 }

    -- Preserve V6 behavior when the source is already on the table: clone it.
    local existing = getObjectFromGUID(guid)
    if existing and existing.type ~= "Bag" and existing.type ~= "Infinite_Bag" then
        local clone = existing.clone({ position = args.position })
        if not clone then error("Could not clone catalog object " .. guid) end
        return { action = "spawn_catalog", guid = guid, object = mcp_object_summary(clone) }
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
                container.takeObject({
                    guid = target_guid,
                    position = { x = 0, y = 8, z = 0 },
                    smooth = false,
                    callback_function = function(category)
                        Wait.frames(function() mcp_catalog_clone(category, args, request_id, container, true) end, 5)
                        Wait.frames(
                        function() if category and not category.isDestroyed() and container and not container.isDestroyed() then
                                container.putObject(category) end end, 20)
                    end
                })
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
        object.setPositionSmooth(args.position or { x = args.x or 0, y = args.y or 2, z = args.z or 0 }, false, true)
        return { action = "place_catalog", guid = guid, object = mcp_object_summary(object) }
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

-- Kill Team setup must not enumerate every object in a large mod. Unrelated
-- scripted objects can be unloading and leave managed references which abort
-- a generic getObjects() walk. Query only the agreed semantic tags, then add
-- bounded exact GUIDs required by the current validation goal.
MCP_HANDLERS.killteam_probe_collection = function(args, request_id)
    local allowed_stages = {
        decode = true,
        tag_lookup = true,
        tag_summary = true,
        required_lookup = true,
        required_summary = true,
        snap_lookup = true,
        snap_summary = true,
    }
    local stage = tostring(args.probe_stage or "")
    if allowed_stages[stage] ~= true then
        error("Kill Team collection probe stage is invalid")
    end
    local probe_index = math.max(1, math.min(tonumber(args.probe_index) or 1, 32))
    local probe_item_index = math.max(1, math.min(tonumber(args.probe_item_index) or 1, 1000))
    local query_tags = mcp_decode_json_array(args.query_tags_json, "query_tags_json")
    local required_guids = mcp_decode_json_array(args.required_guids_json, "required_guids_json")
    local snap_point_tags = mcp_decode_json_array(args.snap_point_tags_json, "snap_point_tags_json")

    if stage == "decode" then
        return {
            stage = stage,
            query_tag_count = #query_tags,
            required_guid_count = #required_guids,
            snap_point_tag_count = #snap_point_tags,
        }
    end

    if stage == "tag_lookup" or stage == "tag_summary" then
        local entity_tag = tostring(query_tags[probe_index] or "")
        if entity_tag == "" or string.len(entity_tag) > 128 then
            error("Kill Team probe query tag is unavailable or invalid")
        end
        local tagged = getObjectsWithTag(entity_tag)
        if type(tagged) ~= "table" then
            error("Kill Team tagged lookup did not return an array")
        end
        if stage == "tag_lookup" then
            return {
                stage = stage,
                probe_index = probe_index,
                entity_tag = entity_tag,
                object_count = #tagged,
            }
        end
        local obj = tagged[probe_item_index]
        if obj == nil then
            return {
                stage = stage,
                probe_index = probe_index,
                probe_item_index = probe_item_index,
                entity_tag = entity_tag,
                object_count = #tagged,
                item_available = false,
            }
        end
        return {
            stage = stage,
            probe_index = probe_index,
            probe_item_index = probe_item_index,
            entity_tag = entity_tag,
            object_count = #tagged,
            item_available = true,
            object = mcp_compact_object_summary(obj),
        }
    end

    if stage == "required_lookup" or stage == "required_summary" then
        local guid = string.lower(tostring(required_guids[probe_index] or ""))
        if not string.match(guid, "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$") then
            error("required Kill Team probe GUID is unavailable or invalid")
        end
        local obj = getObjectFromGUID(guid)
        if obj == nil then
            return {
                stage = stage,
                probe_index = probe_index,
                guid = guid,
                object_available = false,
            }
        end
        if stage == "required_lookup" then
            return {
                stage = stage,
                probe_index = probe_index,
                guid = guid,
                object_available = true,
            }
        end
        return {
            stage = stage,
            probe_index = probe_index,
            guid = guid,
            object_available = true,
            object = mcp_compact_object_summary(obj),
        }
    end

    local global_snap_points = Global.getSnapPoints()
    if type(global_snap_points) ~= "table" then
        error("Global snap points could not be inspected")
    end
    if stage == "snap_lookup" then
        return {
            stage = stage,
            snap_point_count = #global_snap_points,
        }
    end

    local snap = global_snap_points[probe_item_index]
    if snap == nil then
        return {
            stage = stage,
            probe_item_index = probe_item_index,
            snap_point_count = #global_snap_points,
            item_available = false,
        }
    end
    return {
        stage = stage,
        probe_item_index = probe_item_index,
        snap_point_count = #global_snap_points,
        requested_tags = snap_point_tags,
        item_available = true,
        snap_point = {
            position = mcp_vector(snap.position),
            rotation = mcp_vector(snap.rotation),
            rotation_snap = snap.rotation_snap,
            tags = snap.tags or {},
        },
    }
end

local function mcp_deployment_object_summary(obj)
    return {
        guid = mcp_try(function() return obj.getGUID() end),
        name = mcp_try(function() return obj.getName() end),
        type = mcp_try(function() return obj.type end),
        tags = mcp_try(function() return obj.getTags() end) or {},
        position = mcp_vector(mcp_try(function() return obj.getPosition() end)),
        locked = mcp_try(function() return obj.getLock() end) == true,
    }
end

local function mcp_is_roster_card_summary(summary)
    local summary_type = string.lower(tostring(summary.type or ""))
    if summary_type == "card" or summary_type == "cardcustom" or summary_type == "deck" then
        return true
    end
    for _, tag in ipairs(summary.tags or {}) do
        local lowered = string.lower(tostring(tag))
        if lowered == "_roster_card" or lowered == "roster card" then
            return true
        end
    end
    return false
end

local function mcp_is_deployment_figurine(summary)
    if mcp_is_roster_card_summary(summary) then
        return false
    end

    local summary_type = string.lower(tostring(summary.type or ""))
    if summary_type == "custom_model" or summary_type == "figurine" then
        return true
    end

    for _, tag in ipairs(summary.tags or {}) do
        local lowered = string.lower(tostring(tag))
        if lowered == "operative" or lowered == "ktuimini" then
            return true
        end
    end

    return false
end

MCP_HANDLERS.killteam_deployment_test_objects = function(args, request_id)
    local wanted_model_name = "plague marine warrior"
    local wanted_target_tag = "_deployment_zone_blue"

    local function resolve_unique_name(name)
        local figurine_matches = {}
        local roster_card_matches = {}
        for _, obj in ipairs(getObjects()) do
            if mcp_live_object(obj) then
                local object_name = string.lower(tostring(
                    mcp_try(function() return obj.getName() end) or ""
                ))
                if string.find(object_name, name, 1, true) ~= nil then
                    local ok, summary = pcall(function()
                        return mcp_deployment_object_summary(obj)
                    end)
                    if ok and type(summary) == "table" then
                        local guid = string.lower(tostring(summary.guid or ""))
                        if guid ~= "" and guid ~= "-1" then
                            if mcp_is_roster_card_summary(summary) then
                                table.insert(roster_card_matches, summary)
                            elseif mcp_is_deployment_figurine(summary) then
                                table.insert(figurine_matches, summary)
                            end
                        end
                    end
                end
            end
        end
        if #figurine_matches ~= 1 then
            error(
                "test deployment name " .. name
                .. " must resolve to exactly one figurine; found "
                .. tostring(#figurine_matches)
                .. " figurines and "
                .. tostring(#roster_card_matches)
                .. " roster cards"
            )
        end
        return figurine_matches[1]
    end

    local function resolve_unique_tag(tag)
        local tagged = mcp_try(function() return getObjectsWithTag(tag) end)
        if type(tagged) ~= "table" then
            error("test deployment tag lookup failed: " .. tag)
        end
        local matches = {}
        for _, obj in ipairs(tagged) do
            if mcp_live_object(obj) then
                local ok, summary = pcall(function()
                    return mcp_deployment_object_summary(obj)
                end)
                if ok and type(summary) == "table" then
                    local guid = string.lower(tostring(summary.guid or ""))
                    if guid ~= "" and guid ~= "-1" then
                        table.insert(matches, summary)
                    end
                end
            end
        end
        if #matches ~= 1 then
            error(
                "test deployment tag " .. tag
                .. " must resolve to exactly one object; found "
                .. tostring(#matches)
            )
        end
        return matches[1]
    end

    local model = resolve_unique_name(wanted_model_name)
    local target = resolve_unique_tag(wanted_target_tag)
    return {
        count = 2,
        total_matching = 2,
        truncated = false,
        observation_scope = "killteam_deployment_test",
        objects = {
            model,
            target,
        },
    }
end

MCP_HANDLERS.killteam_deployment_name_search = function(args, request_id)
    local name_needles = {
        "plague marine",
        "novitiate dialogus",
        "novitiate hospitaller",
        "blue die",
        "blue kustom 40k dice roller",
        "deployment",
    }
    local matches = {}
    local total_matching = 0
    for _, obj in ipairs(getObjects()) do
        if mcp_live_object(obj) then
            local ok, summary = pcall(function()
                return mcp_deployment_object_summary(obj)
            end)
            if ok and type(summary) == "table" then
                local object_name = string.lower(tostring(summary.name or ""))
                for _, needle in ipairs(name_needles) do
                    if string.find(object_name, needle, 1, true) ~= nil then
                        total_matching = total_matching + 1
                        if #matches < 20 then
                            table.insert(matches, summary)
                        end
                        break
                    end
                end
            end
        end
    end
    return {
        count = #matches,
        total_matching = total_matching,
        truncated = total_matching > #matches,
        observation_scope = "killteam_deployment_name_search",
        objects = matches,
    }
end

MCP_HANDLERS.killteam_setup_roster_cards = function(args, request_id)
    local zone_guid = "aefe3b"
    local zone = mcp_require_object(zone_guid)
    local objects = mcp_try(function()
        return zone.getObjects(false)
    end)
    local cards = {}
    for index, obj in ipairs(objects) do
        if mcp_live_object(obj) then
            local ok, summary = pcall(function()
                return mcp_compact_object_summary(obj)
            end)
            if ok and type(summary) == "table" then
                summary.layout_index = index
                table.insert(cards, summary)
            end
        end
    end
    return {
        zone_guid = zone_guid,
        zone_name = mcp_try(function() return zone.getName() end),
        order_source = "layout_zone.getObjects",
        count = #cards,
        objects = cards,
    }
end

MCP_HANDLERS.killteam_list_objects = function(args, request_id)
    local max_results = math.max(1, math.min(tonumber(args.max_results) or 200, 1000))
    local query_tags = mcp_decode_json_array(args.query_tags_json, "query_tags_json")
    local required_guids = mcp_decode_json_array(args.required_guids_json, "required_guids_json")
    local snap_point_tags = mcp_decode_json_array(args.snap_point_tags_json, "snap_point_tags_json")
    if type(query_tags) ~= "table" or type(required_guids) ~= "table"
        or type(snap_point_tags) ~= "table" then
        error("Kill Team snapshot collection arguments must decode to arrays")
    end
    local generic_query = #query_tags == 0
    if generic_query then
        query_tags = {
            "tts_mcp:entity=operative",
            "tts_mcp:entity=die",
            "tts_mcp:entity=dice_roller",
            "tts_mcp:entity=counter",
            "tts_mcp:entity=calibration",
            "tts_mcp:entity=terrain",
            "tts_mcp:entity=deployment",
            "tts_mcp:entity=objective",
        }
    end
    -- Some older setup callers still mirror the Save 131 placeholder GUID
    -- even when the live scene does not contain that object. If the scene
    -- lacks the sentinel, treat the request as generic setup instead of
    -- aborting before observation can begin.
    if generic_query and #required_guids == 1 and #snap_point_tags == 0 then
        local required_guid = string.lower(tostring(required_guids[1] or ""))
        if required_guid == "96fe20" and getObjectFromGUID(required_guid) == nil then
            required_guids = {}
        end
    end
    local results = {}
    local seen = {}
    local total_matching = 0

    local function add_object(obj)
        if not mcp_live_object(obj) then
            return false
        end
        local summary_ok, summary = pcall(function()
            return mcp_compact_object_summary(obj)
        end)
        if not summary_ok or type(summary) ~= "table" then
            return false
        end
        local guid = tostring(summary.guid or "")
        if guid == "" or guid == "-1" then
            return false
        end
        local key = string.lower(guid)
        if seen[key] then
            return true
        end
        seen[key] = true
        total_matching = total_matching + 1
        if #results < max_results then
            table.insert(results, summary)
        end
        return true
    end

    for index, entity_tag in ipairs(query_tags) do
        if index > 32 then
            break
        end
        entity_tag = tostring(entity_tag or "")
        if entity_tag == "" or string.len(entity_tag) > 128 then
            error("Kill Team query tag is invalid")
        end
        local tagged = mcp_try(function() return getObjectsWithTag(entity_tag) end)
        if type(tagged) == "table" then
            for _, obj in ipairs(tagged) do
                add_object(obj)
            end
        end
    end

    for index, raw_guid in ipairs(required_guids) do
        if index > 32 then
            break
        end
        local guid = string.lower(tostring(raw_guid or ""))
        if not string.match(guid, "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$") then
            error("required Kill Team GUID is invalid: " .. guid)
        end
        local obj = getObjectFromGUID(guid)
        if obj == nil then
            error("required Kill Team object is not in the scene: " .. guid)
        end
        if not add_object(obj) then
            error("required Kill Team object could not be inspected: " .. guid)
        end
    end

    local requested_snap_tags = {}
    for index, raw_tag in ipairs(snap_point_tags) do
        if index > 16 then
            break
        end
        local tag = tostring(raw_tag or "")
        if tag == "" or string.len(tag) > 128 then
            error("Kill Team snap point tag is invalid")
        end
        requested_snap_tags[string.lower(tag)] = true
    end
    local snap_points = {}
    if next(requested_snap_tags) ~= nil then
        local global_snap_points = mcp_try(function() return Global.getSnapPoints() end)
        if type(global_snap_points) ~= "table" then
            error("Global snap points could not be inspected")
        end
        for _, snap in ipairs(global_snap_points) do
            local matched = false
            for _, raw_tag in ipairs(snap.tags or {}) do
                if requested_snap_tags[string.lower(tostring(raw_tag))] then
                    matched = true
                    break
                end
            end
            if matched then
                table.insert(snap_points, {
                    position = mcp_vector(snap.position),
                    rotation = mcp_vector(snap.rotation),
                    rotation_snap = snap.rotation_snap,
                    tags = snap.tags or {},
                })
            end
        end
    end

    return {
        count = #results,
        total_matching = total_matching,
        truncated = total_matching > #results,
        objects = results,
        snap_points = snap_points,
        observation_scope = "killteam_tagged",
    }
end

MCP_HANDLERS.killteam_save_131_setup_objects = function(args, request_id)
    -- The Save 131 fixture is stable and bounded. Keeping these filters in
    -- Lua avoids TTS's managed External Editor wrappers for collection fields.
    return MCP_HANDLERS.killteam_deployment_test_objects(args, request_id)
end

MCP_HANDLERS.killteam_get_roster = function(args, request_id)
    local container = mcp_require_object(args.guid)
    local items = mcp_container_items(container)
    if items == nil then
        error("Object " .. tostring(args.guid) .. " is not a supported roster container")
    end
    return {
        container_guid = tostring(container.getGUID()),
        container = mcp_compact_object_summary(container),
        count = items.count,
        total = items.total,
        truncated = items.truncated,
        items = items.items,
    }
end

MCP_HANDLERS.killteam_probe_los = function(args, request_id)
    local observer = mcp_require_object(args.observer_guid)
    local target = mcp_require_object(args.target_guid)
    local observer_guid = tostring(observer.getGUID())
    local target_guid = tostring(target.getGUID())
    if observer_guid == target_guid then
        error("observer and target must be different objects")
    end

    local eye_local = {
        x = tonumber(args.eye_x) or 0,
        y = tonumber(args.eye_y) or 1,
        z = tonumber(args.eye_z) or 0,
    }
    local eye_world = observer.positionToWorld(eye_local)

    local bounds = mcp_try(function() return target.getBounds() end)
    if type(bounds) ~= "table" or bounds.center == nil or bounds.size == nil then
        error("target bounds are unavailable for line of sight sampling")
    end
    local center = mcp_vector(bounds.center)
    local size = mcp_vector(bounds.size)
    if center == nil or size == nil then
        error("target bounds are invalid for line of sight sampling")
    end

    local function normalize(value, fallback)
        local length = math.sqrt((value.x or 0) ^ 2 + (value.y or 0) ^ 2 + (value.z or 0) ^ 2)
        if length <= 0 then
            return fallback
        end
        return { x = value.x / length, y = value.y / length, z = value.z / length }
    end
    local function add_scaled(first, second, amount)
        return {
            x = first.x + second.x * amount,
            y = first.y + second.y * amount,
            z = first.z + second.z * amount,
        }
    end
    local function subtract(first, second)
        return {
            x = first.x - second.x,
            y = first.y - second.y,
            z = first.z - second.z,
        }
    end

    local right = normalize(
        mcp_vector(mcp_try(function() return target.getTransformRight() end)) or { x = 1, y = 0, z = 0 },
        { x = 1, y = 0, z = 0 }
    )
    local up = normalize(
        mcp_vector(mcp_try(function() return target.getTransformUp() end)) or { x = 0, y = 1, z = 0 },
        { x = 0, y = 1, z = 0 }
    )
    local half_width = math.abs(tonumber(size.x) or 0) / 2
    local half_height = math.abs(tonumber(size.y) or 0) / 2
    local sample_pattern = {
        { -1, -1 }, { 0, -1 }, { 1, -1 },
        { -1, 0 }, { 0, 0 }, { 1, 0 },
        { -1, 1 }, { 0, 1 }, { 1, 1 },
    }
    local ignored = { [observer_guid] = true }
    if type(args.ignore_guids) == "table" then
        for index, guid in ipairs(args.ignore_guids) do
            if index > 16 then
                break
            end
            ignored[tostring(guid)] = true
        end
    end

    local samples = {}
    local blocker_guids = {}
    local blocker_seen = {}
    local visible_rays = 0
    for index, offsets in ipairs(sample_pattern) do
        local target_point = add_scaled(
            add_scaled(center, right, offsets[1] * half_width),
            up,
            offsets[2] * half_height
        )
        local delta = subtract(target_point, eye_world)
        local distance = math.sqrt(delta.x * delta.x + delta.y * delta.y + delta.z * delta.z)
        if distance <= 0.0001 then
            error("observer and target sample point are coincident")
        end
        local direction = {
            x = delta.x / distance,
            y = delta.y / distance,
            z = delta.z / distance,
        }
        local cast_ok, hits = pcall(function()
            return Physics.cast({
                origin = eye_world,
                direction = direction,
                type = 1,
                max_distance = distance,
                debug = args.debug == true,
            })
        end)
        if not cast_ok then
            error("Physics.cast failed: " .. tostring(hits))
        end

        local first_hit = nil
        for _, hit in ipairs(hits or {}) do
            local hit_object = hit and hit.hit_object or nil
            local hit_guid = hit_object and mcp_try(function() return hit_object.getGUID() end) or nil
            if hit_guid ~= nil and not ignored[tostring(hit_guid)] then
                first_hit = {
                    guid = tostring(hit_guid),
                    name = hit_object and mcp_try(function() return hit_object.getName() end) or nil,
                    point = mcp_vector(hit.point),
                    distance = tonumber(hit.distance),
                }
                break
            end
        end
        local hits_target = first_hit ~= nil and first_hit.guid == target_guid
        if hits_target then
            visible_rays = visible_rays + 1
        elseif first_hit ~= nil and not blocker_seen[first_hit.guid] then
            blocker_seen[first_hit.guid] = true
            table.insert(blocker_guids, first_hit.guid)
        end
        table.insert(samples, {
            index = index,
            target_point = target_point,
            hit_guid = first_hit and first_hit.guid or nil,
            hit_name = first_hit and first_hit.name or nil,
            hit_point = first_hit and first_hit.point or nil,
            hit_distance = first_hit and first_hit.distance or nil,
            hits_target = hits_target,
        })
    end

    return {
        observer_guid = observer_guid,
        target_guid = target_guid,
        eye_local = eye_local,
        eye_world = mcp_vector(eye_world),
        target_bounds = mcp_bounds(bounds),
        visible = visible_rays > 0,
        visible_rays = visible_rays,
        total_rays = #sample_pattern,
        visibility_fraction = visible_rays / #sample_pattern,
        blocker_guids = blocker_guids,
        samples = samples,
        collider_warning = "physics_colliders_only",
        debug = args.debug == true,
    }
end

MCP_HANDLERS.killteam_roll_dice = function(args, request_id)
    local roller = mcp_require_object(args.roller_guid)
    local dice_guids = mcp_decode_json_array(args.dice_guids_json, "dice_guids_json")
    if type(dice_guids) ~= "table" or #dice_guids == 0 or #dice_guids > 12 then
        error("dice_guids must contain at least one die GUID")
    end
    local team = tostring(args.team or "")
    local requested = {}
    local pending_dice = {}
    local roller_position = mcp_vector(mcp_try(function() return roller.getPosition() end))
        or { x = 0, y = 3, z = 0 }
    for index, guid in ipairs(dice_guids) do
        guid = string.lower(tostring(guid or ""))
        if not string.match(guid, "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$") then
            error("Kill Team die GUID is invalid: " .. guid)
        end
        local die = mcp_try(function() return getObjectFromGUID(guid) end)
        if die == nil then
            -- A prior failed mechanical attempt may have placed a requested
            -- die inside the roller. Release only that exact GUID before
            -- using the native Roll command below.
            local contained = false
            for _, item in ipairs(mcp_try(function() return roller.getObjects() end) or {}) do
                if string.lower(tostring(item.guid or "")) == guid then
                    contained = true
                    break
                end
            end
            if not contained then
                error("requested die is not in the scene or the selected roller: " .. guid)
            end
            roller.takeObject({
                guid = guid,
                position = {
                    x = roller_position.x + index * 1.5,
                    y = roller_position.y + 3,
                    z = roller_position.z,
                },
                smooth = false,
            })
        end
        if die ~= nil then
            local has_canonical_tag = mcp_has_tag(die, "tts_mcp:entity=die")
            local has_native_tag = args.die_tag ~= nil
                and args.die_tag ~= ""
                and mcp_has_tag(die, args.die_tag)
            if not has_canonical_tag and not has_native_tag then
                error("Object " .. tostring(guid) .. " is not tagged as a Kill Team die")
            end
            if team ~= "" and not has_native_tag and not mcp_has_tag(die, "tts_mcp:team=" .. team) then
                error("Die " .. tostring(guid) .. " is not assigned to team " .. team)
            end
        end
        requested[guid] = true
        table.insert(pending_dice, guid)
    end

    Wait.frames(function()
        for _, guid in ipairs(pending_dice) do
            mcp_require_object(guid).roll()
        end
        -- Native rolls are asynchronous; wait for all dice to settle before
        -- reading their upward face values.
        Wait.frames(function()
            local faces = {}
            local items = {}
            for _, raw_guid in ipairs(dice_guids) do
                local guid = string.lower(tostring(raw_guid))
                local face = mcp_die_value(mcp_require_object(guid))
                table.insert(faces, face)
                table.insert(items, {
                    guid = guid,
                    die_value = face,
                })
            end
            mcp_send_ok(request_id, {
                team = team,
                purpose = tostring(args.purpose or ""),
                roller_guid = args.roller_guid,
                faces = faces,
                items = items,
                roll_method = "native_die_roll",
            })
        end, 120)
    end, 15)
    return nil, true
end

MCP_HANDLERS.killteam_read_dice_values = function(args, request_id)
    -- Read a committed physical roll without moving, rerolling, or otherwise
    -- changing the dice. This is the recovery path when a deferred roller
    -- response arrived before its object-script callbacks had settled.
    local roller = mcp_require_object(args.roller_guid)
    local dice_guids = mcp_decode_json_array(args.dice_guids_json, "dice_guids_json")
    if type(dice_guids) ~= "table" or #dice_guids == 0 or #dice_guids > 12 then
        error("dice_guids must contain at least one die GUID")
    end
    local rolled_values = mcp_try(function() return roller.getTable("diceGuids") end) or {}
    local faces = {}
    local items = {}
    for _, raw_guid in ipairs(dice_guids) do
        local guid = string.lower(tostring(raw_guid or ""))
        if not string.match(guid, "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$") then
            error("Kill Team die GUID is invalid: " .. guid)
        end
        local face = tonumber(rolled_values[guid])
        if face == nil then
            face = mcp_die_value(mcp_require_object(guid))
        end
        table.insert(faces, face)
        table.insert(items, { guid = guid, die_value = face })
    end
    return {
        roller_guid = tostring(roller.getGUID()),
        faces = faces,
        items = items,
        settled = not (#faces == 0 or #faces ~= #dice_guids),
    }
end

MCP_HANDLERS.killteam_observe_defense_roll = function(args, request_id)
    local station = mcp_require_object(args.station_guid)
    local expected_count = tonumber(args.expected_count)
    if expected_count == nil or expected_count < 1 or expected_count > 6
        or expected_count ~= math.floor(expected_count) then
        error("expected_count must be an integer from 1 through 6")
    end
    local rolled_values = mcp_try(function() return station.getTable("diceGuids") end)
    if type(rolled_values) ~= "table" then
        error("the defense station has no readable completed roll")
    end
    local items = {}
    for raw_guid, raw_face in pairs(rolled_values) do
        local guid = string.lower(tostring(raw_guid or ""))
        local face = tonumber(raw_face)
        if string.match(guid, "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$")
            and face ~= nil and face >= 1 and face <= 6 then
            table.insert(items, { guid = guid, die_value = face })
        end
    end
    table.sort(items, function(first, second) return first.guid < second.guid end)
    if #items ~= expected_count then
        error(
            "the defense station must contain exactly "
            .. tostring(expected_count)
            .. " completed die results"
        )
    end
    local faces = {}
    for _, item in ipairs(items) do
        table.insert(faces, item.die_value)
    end
    return {
        station_guid = tostring(station.getGUID()),
        expected_count = expected_count,
        faces = faces,
        items = items,
    }
end

local function mcp_operative_wounds(operative)
    local state = mcp_try(function() return operative.getTable("state") end)
    if type(state) ~= "table" then
        state = mcp_try(function() return operative.getVar("state") end)
    end
    if type(state) ~= "table" then
        return nil
    end
    return tonumber(state.wounds)
end

MCP_HANDLERS.killteam_apply_damage = function(args, request_id)
    local operative = mcp_require_object(args.guid)
    local damage = tonumber(args.damage)
    local expected_wounds = tonumber(args.expected_wounds)
    if damage == nil or damage < 0 or damage > 100 or damage ~= math.floor(damage) then
        error("damage must be an integer from 0 through 100")
    end
    if expected_wounds == nil or expected_wounds < 0
        or expected_wounds ~= math.floor(expected_wounds) then
        error("expected_wounds must be a non-negative integer")
    end
    local before_wounds = mcp_operative_wounds(operative)
    if before_wounds == nil then
        error("operative wound state is not readable")
    end
    if before_wounds ~= expected_wounds then
        error(
            "operative wound precondition failed: expected "
            .. tostring(expected_wounds)
            .. ", observed "
            .. tostring(before_wounds)
        )
    end
    for _ = 1, math.min(damage, before_wounds) do
        operative.call("damage", "Blue")
    end
    local after_wounds = mcp_operative_wounds(operative)
    local expected_after = math.max(0, before_wounds - damage)
    if after_wounds ~= expected_after then
        error(
            "operative wound readback failed: expected "
            .. tostring(expected_after)
            .. ", observed "
            .. tostring(after_wounds)
        )
    end
    return {
        guid = tostring(operative.getGUID()),
        damage = damage,
        before_wounds = before_wounds,
        after_wounds = after_wounds,
    }
end

MCP_HANDLERS.set_counter_value = function(args, request_id)
    local counter = mcp_require_object(args.guid)
    if counter.Counter == nil or counter.Counter.setValue == nil then
        error("Object " .. tostring(args.guid) .. " is not a TTS counter")
    end
    local value = tonumber(args.value)
    if value == nil then
        error("counter value must be numeric")
    end
    counter.Counter.setValue(value)
    return {
        guid = args.guid,
        value = mcp_counter_value(counter),
        object = mcp_object_summary(counter),
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
    local position = { x = x, y = y, z = z }

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
        position = args.position or { x = 0, y = 3, z = 0 },
        rotation = args.rotation or { x = 0, y = 0, z = 0 },
        scale = args.scale or { x = 1, y = 1, z = 1 },
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
    broadcastToAll(message, { r = 1, g = 1, b = 1 })
    return { broadcast = true, message = message }
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

local function mcp_external_scalar_array(data, count_field, item_prefix, max_items)
    local raw_count = mcp_try(function() return data[count_field] end)
    local count = math.max(
        0,
        math.min(tonumber(tostring(raw_count or "0")) or 0, max_items)
    )
    local values = {}
    for index = 1, count do
        local field = item_prefix .. tostring(index)
        local raw_value = mcp_try(function() return data[field] end)
        local value = tostring(raw_value or "")
        if value == "" then
            error(field .. " is missing")
        end
        table.insert(values, value)
    end
    return values
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

    if action == "killteam_deployment_test_objects"
        or action == "killteam_deployment_name_search"
        or action == "killteam_setup_roster_cards"
        or action == "killteam_save_131_setup_objects" then
        local handler = MCP_HANDLERS[action]
        mcp_debug("[tts-mcp] received action: " .. action)
        local ok, result, deferred = pcall(handler, {}, request_id)
        if not ok then
            mcp_send_error(request_id, result)
        elseif deferred ~= true then
            mcp_send_ok(request_id, result)
        end
        return true
    end

    if action == "get_object" or action == "get_snap_points" then
        local scalar_args = {
            guid = tostring(data.guid or ""),
        }
        local handler = MCP_HANDLERS[action]
        mcp_debug("[tts-mcp] received action: " .. action)
        if handler == nil then
            mcp_send_error(request_id, "Unknown MCP action: " .. action)
            return true
        end
        local ok, result, deferred = pcall(handler, scalar_args, request_id)
        if not ok then
            mcp_send_error(request_id, result)
        elseif deferred ~= true then
            mcp_send_ok(request_id, result)
        end
        return true
    end

    -- Reconstruct Kill Team collection arrays from bounded root scalar slots.
    -- TTS exposes JSON strings inside object-form External Editor messages as
    -- managed values which can throw before JSON.decode or Lua pcall runs.
    if action == "killteam_list_objects" then
        local raw_max_results = mcp_try(function() return data.max_results end)
        local query_tags = mcp_external_scalar_array(
            data, "query_tag_count", "query_tag_", 32
        )
        local required_guids = mcp_external_scalar_array(
            data, "required_guid_count", "required_guid_", 32
        )
        local snap_point_tags = mcp_external_scalar_array(
            data, "snap_point_tag_count", "snap_point_tag_", 16
        )
        local list_args = {
            max_results = tonumber(tostring(raw_max_results or "200")) or 200,
            query_tags_json = JSON.encode(query_tags),
            required_guids_json = JSON.encode(required_guids),
            snap_point_tags_json = JSON.encode(snap_point_tags),
        }
        local handler = MCP_HANDLERS[action]
        mcp_debug("[tts-mcp] received action: " .. action)
        if handler == nil then
            mcp_send_error(request_id, "Unknown MCP action: " .. action)
            return true
        end
        local ok, result, deferred = pcall(handler, list_args, request_id)
        if not ok then
            mcp_send_error(request_id, result)
        elseif deferred ~= true then
            mcp_send_ok(request_id, result)
        end
        return true
    end

    local nested_args = mcp_try(function() return data.args end)
    local args = {}
    -- Object-form External Editor messages can expose nested scalar values as
    -- managed MoonSharp wrappers. Python mirrors the scalar fields at the
    -- message root, so prefer those plain values even when the nested field
    -- appears present. This is especially important for the Kill Team JSON
    -- filter arguments: passing a managed wrapper to JSON.decode causes TTS
    -- to raise "Object reference not set to an instance of an object" with
    -- guid=-1 before the handler can return a correlated MCP error.
    local scalar_fallback_fields = {
        "max_results",
        "query_tags_json",
        "required_guids_json",
        "snap_point_tags_json",
        "probe_stage",
        "probe_index",
        "probe_item_index",
        "observer_guid",
        "target_guid",
        "eye_x",
        "eye_y",
        "eye_z",
        "debug",
        "team",
        "dice_guids_json",
        "roller_guid",
        "purpose",
        "die_tag",
        "station_guid",
        "expected_count",
        "damage",
        "expected_wounds",
    }
    local external_fields = {
        "guid",
        "name_contains",
        "tag",
        "compact",
        "position",
        "rotation",
        "locked",
        "include_self",
        "minimum",
        "maximum",
        "from_guid",
        "to_guid",
        "ignore_tags",
        "container_guid",
        "flip",
        "smooth",
        "index",
        "item_guid",
        "container_path",
        "master_bag_guid",
        "container_name",
        "object_guid",
        "ignore_guids",
        "value",
        "player_color",
        "mode",
        "pitch",
        "yaw",
        "distance",
        "collide",
        "fast",
        "name",
        "object_type",
        "scale",
        "message",
    }
    for _, field in ipairs(scalar_fallback_fields) do
        table.insert(external_fields, field)
    end
    for _, field in ipairs(external_fields) do
        local value = mcp_try(function() return data[field] end)
        if value == nil and nested_args ~= nil then
            value = mcp_try(function() return nested_args[field] end)
        end
        if value ~= nil then
            args[field] = value
        end
    end
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
    -- Managed object-reference failures can occur outside a handler's local
    -- pcall while TTS is unloading an object. Keep the External Editor
    -- request correlated so Python receives an error response instead of
    -- waiting for its timeout.
    local ok, err = pcall(mcp_handleExternalMessage, data)
    if ok then
        return
    end

    local request_id = ""
    local decoded_ok, decoded = pcall(mcp_unwrap_external_message, data)
    if decoded_ok and type(decoded) == "table" then
        request_id = tostring(decoded.requestId or "")
    end
    local sent, send_err = pcall(
        mcp_send_error,
        request_id,
        "Unhandled MCP bridge dispatch error: " .. tostring(err)
    )
    if not sent then
        print("[tts-mcp] failed to return dispatch error: " .. tostring(send_err))
    end
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
                printToAll(text, { r = 1, g = 1, b = 1, a = 1 })
            end
        end
    )
    -- Do not consume the original player message. Returning nil preserves
    -- TTS's normal chat rendering while the AI reply is handled separately.
    return nil
end
