-- Placement-only Tabletop Simulator bridge for Kill Team setup.
-- Install this in the loaded game's Global script when the full Kill Team
-- runtime is unavailable or too large for the current workflow.

local MCP_CHANNEL = "tts-mcp"
local MCP_BRIDGE_VERSION = "2026-07-29-setup-placement-v1"

local function mcp_try(fn)
    local ok, value = pcall(fn)
    if ok then
        return value
    end
    return nil
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
    data = mcp_decode_message(data)
    if type(data) == "table" and tostring(data.messageID or "") == "2" then
        data = mcp_decode_message(data.customMessage)
    end
    return data
end

local function mcp_trim(value)
    local text = tostring(value or "")
    local first = 1
    local last = #text
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

local function mcp_json_safe(value)
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
        for key, item in pairs(value) do
            if type(key) == "string" or type(key) == "number" then
                safe[key] = mcp_json_safe(item)
            end
        end
        return safe
    end
    return tostring(value)
end

local function mcp_send_response(response)
    local encoded = nil
    local encoded_ok, encoded_value = pcall(function() return JSON.encode(response) end)
    if encoded_ok then
        encoded = encoded_value
    end

    local _ = pcall(function()
        sendExternalMessage(response)
    end)

    if encoded ~= nil then
        pcall(function()
            print("[tts-mcp-response]" .. encoded)
        end)
    end
end

local function mcp_send_ok(request_id, result)
    mcp_send_response({
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = true,
        result = mcp_json_safe(result),
    })
end

local function mcp_send_error(request_id, err)
    mcp_send_response({
        channel = MCP_CHANNEL,
        event = "mcp_response",
        requestId = request_id,
        ok = false,
        error = tostring(err),
    })
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

local function mcp_object_summary(obj)
    return {
        guid = mcp_try(function() return obj.getGUID() end),
        name = mcp_try(function() return obj.getName() end),
        type = mcp_try(function() return obj.type end) or mcp_try(function() return obj.tag end),
        tags = mcp_try(function() return obj.getTags() end) or {},
        position = mcp_try(function() return obj.getPosition() end),
        locked = mcp_try(function() return obj.getLock() end),
    }
end

local function mcp_matches_filters(obj, args)
    local name_filter = string.lower(tostring(args.name_contains or ""))
    local tag_filter = tostring(args.tag or "")
    local object_name = string.lower(tostring(mcp_try(function() return obj.getName() end) or ""))
    if name_filter ~= "" and string.find(object_name, name_filter, 1, true) == nil then
        return false
    end
    if tag_filter == "" then
        return true
    end
    local tags = mcp_try(function() return obj.getTags() end) or {}
    for _, actual in ipairs(tags) do
        if string.lower(tostring(actual)) == string.lower(tag_filter) then
            return true
        end
    end
    return false
end

local MCP_HANDLERS = {}

function onLoad()
    mcp_try(function()
        printToAll("Kill Team setup placement bridge loaded.", { r = 0.85, g = 0.95, b = 1, a = 1 })
    end)
end

MCP_HANDLERS.setup_ping = function(args, request_id)
    local object_count = mcp_try(function() return #getObjects() end)
    mcp_try(function()
        printToAll("Kill Team setup placement bridge is active.", { r = 0.9, g = 0.95, b = 1, a = 1 })
    end)
    return {
        bridge = MCP_CHANNEL,
        bridge_version = MCP_BRIDGE_VERSION,
        object_count = tonumber(object_count) or -1,
        message = "Kill Team setup placement bridge is active.",
    }
end

MCP_HANDLERS.setup_list_objects = function(args, request_id)
    local max_results = math.max(1, math.min(tonumber(args.max_results) or 200, 1000))
    local compact = args.compact ~= false
    local results = {}
    local total_matching = 0
    local objects_ok, objects_or_error = pcall(getObjects)
    if not objects_ok then
        error("TTS scene enumeration failed: " .. tostring(objects_or_error))
    end
    if type(objects_or_error) ~= "table" then
        error("TTS scene enumeration returned an invalid object list")
    end
    for _, obj in ipairs(objects_or_error) do
        local live_guid = mcp_try(function() return obj.getGUID() end)
        if live_guid ~= nil and tostring(live_guid) ~= "" and tostring(live_guid) ~= "-1" and mcp_matches_filters(obj, args) then
            total_matching = total_matching + 1
            local summary = compact and mcp_object_summary(obj) or {
                guid = mcp_try(function() return obj.getGUID() end),
                name = mcp_try(function() return obj.getName() end),
                description = mcp_try(function() return obj.getDescription() end),
                type = mcp_try(function() return obj.type end) or mcp_try(function() return obj.tag end),
                tags = mcp_try(function() return obj.getTags() end) or {},
                position = mcp_try(function() return obj.getPosition() end),
                rotation = mcp_try(function() return obj.getRotation() end),
                locked = mcp_try(function() return obj.getLock() end),
            }
            if #results < max_results then
                table.insert(results, summary)
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

MCP_HANDLERS.setup_place_model = function(args, request_id)
    local obj = mcp_require_object(args.guid)
    local requested = args.position
    if type(requested) ~= "table" then
        error("position must be a table containing x, y, and z.")
    end

    local x = tonumber(requested.x or requested[1])
    local y = tonumber(requested.y or requested[2])
    local z = tonumber(requested.z or requested[3])
    if x == nil or y == nil or z == nil then
        error("position must contain numeric x, y, and z values.")
    end

    local position = { x = x, y = y, z = z }
    if args.smooth == true then
        obj.setPositionSmooth(position, args.collide == true, args.fast ~= false)
    else
        obj.setPosition(position)
    end

    local guid = obj.getGUID()
    Wait.frames(function()
        local moved = getObjectFromGUID(guid)
        local actual = moved and moved.getPosition() or position
        mcp_send_ok(request_id, {
            status = "verified",
            guid = guid,
            name = moved and moved.getName() or mcp_try(function() return obj.getName() end),
            tags = moved and moved.getTags() or mcp_try(function() return obj.getTags() end) or {},
            position = {
                x = tonumber(actual.x) or x,
                y = tonumber(actual.y) or y,
                z = tonumber(actual.z) or z,
            },
        })
    end, 20)
    return nil, true
end

function mcp_handleExternalMessage(data)
    data = mcp_unwrap_external_message(data)
    if type(data) ~= "table" or data.channel ~= MCP_CHANNEL then
        return false
    end

    local request_id = tostring(data.requestId or "")
    local action = tostring(data.action or "")
    local handler = MCP_HANDLERS[action]
    if handler == nil then
        mcp_send_error(request_id, "Unknown placement MCP action: " .. action)
        return true
    end

    local args = {}
    local nested_args = mcp_try(function() return data.args end)
    for _, field in ipairs({ "guid", "name_contains", "tag", "max_results", "compact", "smooth", "collide", "fast", "position" }) do
        local value = mcp_try(function() return data[field] end)
        if value == nil and nested_args ~= nil then
            value = mcp_try(function() return nested_args[field] end)
        end
        if value ~= nil then
            args[field] = value
        end
    end

    local ok, result, deferred = pcall(handler, args, request_id)
    if not ok then
        mcp_send_error(request_id, result)
    elseif deferred ~= true then
        mcp_send_ok(request_id, result)
    end
    return true
end

function onExternalMessage(data)
    local ok, err = pcall(mcp_handleExternalMessage, data)
    if ok then
        return
    end
    local request_id = ""
    local decoded = mcp_unwrap_external_message(data)
    if type(decoded) == "table" then
        request_id = tostring(decoded.requestId or "")
    end
    local sent = pcall(mcp_send_error, request_id, "Unhandled setup bridge dispatch error: " .. tostring(err))
    if not sent then
        print("[tts-killteam-setup] failed to return dispatch error: " .. tostring(err))
    end
end
