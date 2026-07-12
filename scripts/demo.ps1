$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://127.0.0.1:8080" }

function Invoke-DemoRequest {
    param (
        [string]$Title,
        [string]$Path,
        [hashtable]$Body
    )

    Write-Host "== $Title =="
    $json = $Body | ConvertTo-Json -Depth 10
    Invoke-RestMethod `
        -Uri "$BaseUrl$Path" `
        -Method Post `
        -ContentType "application/json" `
        -Body $json |
        ConvertTo-Json -Depth 10
    Write-Host ""
}

Write-Host "== health =="
Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get | ConvertTo-Json -Depth 10
Write-Host ""

Invoke-DemoRequest `
    -Title "check logical SQL" `
    -Path "/api/v1/sql/check" `
    -Body @{
        request_id = "demo-check-user"
        operator = "ai-agent"
        scene = "demo"
        sql = "select uid, user_name from user where uid = 10001 limit 10"
        route_context = @{}
    }

Invoke-DemoRequest `
    -Title "execute approved SQL" `
    -Path "/api/v1/sql/execute" `
    -Body @{
        request_id = "demo-execute-user"
        operator = "ai-agent"
        scene = "demo"
        sql = "select uid, user_name from user where uid = 10001 limit 1"
        route_context = @{}
    }

Invoke-DemoRequest `
    -Title "reject unsafe SQL" `
    -Path "/api/v1/sql/check" `
    -Body @{
        request_id = "demo-reject-update"
        operator = "ai-agent"
        scene = "demo"
        sql = "update user set status = 0 where uid = 10001"
        route_context = @{}
    }

Invoke-DemoRequest `
    -Title "check Redis GET" `
    -Path "/api/v1/redis/check" `
    -Body @{
        request_id = "demo-redis-check"
        operator = "ai-agent"
        scene = "demo"
        command = "GET"
        args = @("demo:user:10001")
        redis_context = @{ catlog_name = "demo" }
    }

Invoke-DemoRequest `
    -Title "execute Redis GET" `
    -Path "/api/v1/redis/execute" `
    -Body @{
        request_id = "demo-redis-execute"
        operator = "ai-agent"
        scene = "demo"
        command = "GET"
        args = @("demo:user:10001")
        redis_context = @{ catlog_name = "demo" }
    }

Invoke-DemoRequest `
    -Title "reject unsafe Redis command" `
    -Path "/api/v1/redis/check" `
    -Body @{
        request_id = "demo-redis-reject"
        operator = "ai-agent"
        scene = "demo"
        command = "SET"
        args = @("demo:user:10001", "alice")
        redis_context = @{ catlog_name = "demo" }
    }
