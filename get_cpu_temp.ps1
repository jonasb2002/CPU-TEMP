# Hardware Temperature Reader using LibreHardwareMonitor
# Reads CPU, GPU and SSD temperatures

param(
    [string]$DllPath = "$PSScriptRoot\LibreHardwareMonitorLib.dll"
)

if (-not (Test-Path $DllPath)) {
    Write-Output '{"error": "DLL_NOT_FOUND"}'
    exit 1
}

try {
    Add-Type -Path $DllPath

    $computer = New-Object LibreHardwareMonitor.Hardware.Computer
    $computer.IsCpuEnabled = $true
    $computer.IsGpuEnabled = $true
    $computer.IsStorageEnabled = $true
    $computer.Open()

    $result = @{
        success = $true
        cpu = @{ name = ""; temp = $null }
        gpu = @{ name = ""; temp = $null }
        ssds = @()
    }

    foreach ($hardware in $computer.Hardware) {
        $hardware.Update()
        
        # CPU
        if ($hardware.HardwareType -eq [LibreHardwareMonitor.Hardware.HardwareType]::Cpu) {
            $result.cpu.name = $hardware.Name
            
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq [LibreHardwareMonitor.Hardware.SensorType]::Temperature) {
                    if ($null -ne $sensor.Value -and $sensor.Name -match "Core") {
                        $temp = [math]::Round($sensor.Value, 1)
                        if ($null -eq $result.cpu.temp -or $temp -gt $result.cpu.temp) {
                            $result.cpu.temp = $temp
                        }
                    }
                }
            }
        }
        
        # GPU (NVIDIA or AMD)
        if ($hardware.HardwareType -eq [LibreHardwareMonitor.Hardware.HardwareType]::GpuNvidia -or
            $hardware.HardwareType -eq [LibreHardwareMonitor.Hardware.HardwareType]::GpuAmd -or
            $hardware.HardwareType -eq [LibreHardwareMonitor.Hardware.HardwareType]::GpuIntel) {
            $result.gpu.name = $hardware.Name
            
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq [LibreHardwareMonitor.Hardware.SensorType]::Temperature) {
                    if ($null -ne $sensor.Value -and $sensor.Value -lt 150) {
                        $temp = [math]::Round($sensor.Value, 1)
                        if ($null -eq $result.gpu.temp -or $temp -gt $result.gpu.temp) {
                            $result.gpu.temp = $temp
                        }
                    }
                }
            }
        }
        
        # Storage (SSD/HDD)
        if ($hardware.HardwareType -eq [LibreHardwareMonitor.Hardware.HardwareType]::Storage) {
            $ssd = @{
                name = $hardware.Name
                temp = $null
            }
            
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq [LibreHardwareMonitor.Hardware.SensorType]::Temperature) {
                    if ($null -ne $sensor.Value) {
                        $ssd.temp = [math]::Round($sensor.Value, 1)
                        break
                    }
                }
            }
            
            if ($null -ne $ssd.temp) {
                $result.ssds += $ssd
            }
        }
    }

    $computer.Close()
    $result | ConvertTo-Json -Compress -Depth 5

} catch {
    @{ error = "EXCEPTION"; message = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
