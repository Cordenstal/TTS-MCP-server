-- Placement-only Tabletop Simulator bridge for Kill Team setup.
-- Install this in the loaded game's Global script when the full Kill Team
-- runtime is unavailable or too large for the current workflow.

local MCP_CHANNEL = "tts-mcp"
local MCP_BRIDGE_VERSION = "2026-07-29-setup-placement-v2-chat"
local MCP_HTTP_CHAT_URL = "http://127.0.0.1:8765/chat"

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

local function mcp_public_chat_text(value)
    local text = mcp_trim(value)
    if text == "" then
        return ""
    end
    -- Gateway responses are already sanitized. Keep this final Lua boundary
    -- from displaying a raw JSON object if a backend is misconfigured.
    local first = string.sub(text, 1, 1)
    if first == "{" or first == "[" then
        return ""
    end
    return text
end

-- Keep this placement-only bridge observable without taking ownership of the
-- full gameplay chat/AI flow. The Python listener records this event in the
-- runtime trace and exposes it through tts_recent_chat/tts_wait_for_chat.
local function mcp_forward_chat(message, sender)
    local text = mcp_trim(message)
    if text == "" then
        return
    end
    local event = {
        channel = MCP_CHANNEL,
        event = "chat_message",
        message = text,
        player_color = sender and tostring(sender.color or "") or "",
        player_name = sender and tostring(sender.steam_name or sender.name or "") or "",
    }
    Wait.frames(function()
        pcall(function()
            sendExternalMessage(event)
        end)
    end, 1)
end

function onChat(message, sender)
    mcp_forward_chat(message, sender)

    local raw_message = mcp_trim(message)
    if raw_message == "" then
        return nil
    end

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
                print("[tts-killteam-setup] chat HTTP error: " .. tostring(request.error))
                return
            end
            if request.response_code < 200 or request.response_code >= 300 then
                print("[tts-killteam-setup] chat HTTP status: " .. tostring(request.response_code))
                return
            end

            local ok, response = pcall(function() return JSON.decode(request.text or "") end)
            if not ok or type(response) ~= "table" then
                print("[tts-killteam-setup] chat response was not valid JSON")
                return
            end
            local text = mcp_public_chat_text(response.text or "")
            if text ~= "" then
                printToAll(text, { r = 1, g = 1, b = 1, a = 1 })
            end
        end
    )
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

local function mcp_object_type(obj)
    return tostring(mcp_try(function() return obj.type end) or mcp_try(function() return obj.tag end) or "")
end

local function mcp_object_tags(obj)
    return mcp_try(function() return obj.getTags() end) or {}
end

local function mcp_is_operative_figurine(obj)
    if string.lower(mcp_object_type(obj)) ~= "figurine" then
        return false
    end
    local tags = mcp_object_tags(obj)
    for _, tag in ipairs(tags) do
        if string.lower(tostring(tag)) == "operative" then
            return true
        end
    end
    return false
end

local function mcp_type_name(value)
    local value_type = type(value)
    if value_type == "table" then
        local parts = { "table" }
        for _, axis in ipairs({ "x", "y", "z" }) do
            local axis_value = mcp_try(function() return value[axis] end)
            if axis_value ~= nil then
                table.insert(parts, axis .. ":" .. type(axis_value))
            end
        end
        return table.concat(parts, ",")
    end
    return value_type
end

local function mcp_type_field(args, field)
    return mcp_type_name(mcp_try(function() return args[field] end))
end

local function mcp_setup_request_summary(args, request_id, action, stage)
    local position = mcp_try(function() return args.position end)
    local parts = {
        "request_id=" .. tostring(request_id or ""),
        "action=" .. tostring(action or ""),
        "stage=" .. tostring(stage or ""),
        "args=" .. mcp_type_name(args),
        "position=" .. mcp_type_name(position),
        "guid=" .. mcp_type_field(args, "guid"),
        "x=" .. mcp_type_field(args, "x"),
        "y=" .. mcp_type_field(args, "y"),
        "z=" .. mcp_type_field(args, "z"),
        "smooth=" .. mcp_type_field(args, "smooth"),
        "collide=" .. mcp_type_field(args, "collide"),
        "fast=" .. mcp_type_field(args, "fast"),
    }
    if type(position) == "table" then
        table.insert(parts, "position.x=" .. mcp_type_field(position, "x"))
        table.insert(parts, "position.y=" .. mcp_type_field(position, "y"))
        table.insert(parts, "position.z=" .. mcp_type_field(position, "z"))
    end
    return "[tts-killteam-setup] " .. table.concat(parts, " ")
end

local function mcp_setup_position_table(args)
    local requested = args.position
    requested = mcp_json_safe(requested)
    if type(requested) ~= "table" then
        requested = args
    end
    if type(requested) ~= "table" then
        requested = {}
    end
    return requested
end

local function mcp_setup_coordinate_value(source, field, index)
    if type(source) ~= "table" then
        return nil
    end
    local value = mcp_try(function() return source[field] end)
    local number = tonumber(value)
    if number ~= nil then
        return number
    end
    if index ~= nil then
        value = mcp_try(function() return source[index] end)
        number = tonumber(value)
        if number ~= nil then
            return number
        end
    end
    return nil
end

local function mcp_setup_requested_position(args)
    local requested = mcp_setup_position_table(args)
    local x = mcp_setup_coordinate_value(requested, "x", 1)
    local y = mcp_setup_coordinate_value(requested, "y", 2)
    local z = mcp_setup_coordinate_value(requested, "z", 3)
    if x ~= nil and y ~= nil and z ~= nil then
        return { x = x, y = y, z = z }, "position"
    end

    x = mcp_setup_coordinate_value(args, "x", 1)
    y = mcp_setup_coordinate_value(args, "y", 2)
    z = mcp_setup_coordinate_value(args, "z", 3)
    if x ~= nil and y ~= nil and z ~= nil then
        return { x = x, y = y, z = z }, "args"
    end

    return nil, "missing"
end

local MCP_HANDLERS = {}

function onLoad()
    mcp_try(function()
        printToAll("Kill Team setup placement bridge loaded.", { r = 0.85, g = 0.95, b = 1, a = 1 })
    end)
end

MCP_HANDLERS.setup_ping = function(args, request_id)
    args = mcp_json_safe(args)
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
    args = mcp_json_safe(args)
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
            if string.lower(tostring(args.tag or "")) == "operative" and not mcp_is_operative_figurine(obj) then
                goto continue
            end
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
        ::continue::
    end
    return {
        count = #results,
        total_matching = total_matching,
        truncated = total_matching > #results,
        objects = results,
    }
end

local function mcp_setup_place_model(args, request_id, action)
    print(mcp_setup_request_summary(args, request_id, action, "pre"))
    args = mcp_json_safe(args)
    print(mcp_setup_request_summary(args, request_id, action, "post"))
    local obj = mcp_require_object(args.guid)
    if not mcp_is_operative_figurine(obj) then
        error(
            "setup placement requires an Operative figurine; got "
            .. mcp_object_type(obj)
            .. " tags="
            .. table.concat(mcp_object_tags(obj), ",")
            .. "; "
            .. mcp_setup_request_summary(args, request_id, action, "reject")
        )
    end
    local position, position_source = mcp_setup_requested_position(args)
    if position == nil then
        error("position must contain numeric x, y, and z values; " .. mcp_setup_request_summary(args, request_id, action, "error"))
    end

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
            source = position_source,
            position = {
                x = tonumber(actual.x) or position.x,
                y = tonumber(actual.y) or position.y,
                z = tonumber(actual.z) or position.z,
            },
        })
        end, 20)
    return nil, true
end

MCP_HANDLERS.setup_place_model = function(args, request_id)
    return mcp_setup_place_model(args, request_id, "setup_place_model")
end

MCP_HANDLERS.move_object = function(args, request_id)
    return mcp_setup_place_model(args, request_id, "move_object")
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
    for _, field in ipairs({ "guid", "name_contains", "tag", "max_results", "compact", "smooth", "collide", "fast", "x", "y", "z", "position" }) do
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
