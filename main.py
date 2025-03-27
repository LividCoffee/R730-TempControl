import sys
import binascii
from pyghmi.ipmi import command
import time
import math
import os
import datetime
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored terminal output
init()

def connect_to_ipmi(hostname, username, password, kg=None):
    """Подключение к IPMI интерфейсу сервера Dell R730"""
    try:
        # Если kg предоставлен как hex-строка, преобразуем в байты
        kg_bytes = None
        if kg:
            try:
                kg_bytes = binascii.unhexlify(kg)
            except binascii.Error:
                # Если не hex-строка, используем как есть
                kg_bytes = kg
                
        ipmi_conn = command.Command(
            bmc=hostname,
            userid=username,
            password=password,
            kg=kg_bytes  # Преобразованный K_g ключ для IPMI 2.0
        )
        return ipmi_conn
    except Exception as e:
        print(f"Ошибка подключения к IPMI: {str(e)}")
        return None

def get_sensor_data(ipmi_conn):
    """Получение данных с сенсоров"""
    sensors = ipmi_conn.get_sensor_data()
    return sensors

def get_temperatures(ipmi_conn):
    """Получение значений температурных сенсоров"""
    sensors = get_sensor_data(ipmi_conn)
    temps = []
    
    for sensor in sensors:
        if sensor.type == 'Temperature' and sensor.value is not None:
            temps.append({
                'name': sensor.name,
                'value': sensor.value,
                'units': sensor.units,
                'health': sensor.health
            })
    
    return temps

def get_fans(ipmi_conn):
    """Получение информации о вентиляторах"""
    sensors = get_sensor_data(ipmi_conn)
    fans = []
    
    for sensor in sensors:
        if sensor.type == 'Fan' and sensor.value is not None:
            fans.append({
                'name': sensor.name,
                'value': sensor.value,
                'units': sensor.units,
                'health': sensor.health
            })
    
    return fans

def get_cpu_temperatures(ipmi_conn):
    """Получение температур процессоров"""
    sensors = get_sensor_data(ipmi_conn)
    cpu_temps = []
    generic_temps = []
    
    # Возможные шаблоны для CPU температурных сенсоров
    cpu_patterns = ['CPU', 'Processor', 'Core', 'Die', 'Package', 'PROC']
    
    # Сначала ищем явно помеченные CPU сенсоры
    for sensor in sensors:
        if sensor.type == 'Temperature' and sensor.value is not None:
            # Проверка имени сенсора на соответствие шаблонам CPU
            if any(pattern.lower() in sensor.name.lower() for pattern in cpu_patterns):
                cpu_temps.append({
                    'name': sensor.name,
                    'value': sensor.value,
                    'units': sensor.units,
                    'health': sensor.health
                })
            # Отдельно собираем все сенсоры с именем "Temp"
            elif sensor.name == 'Temp':
                generic_temps.append({
                    'name': f"CPU {len(generic_temps)+1} ({sensor.name})",
                    'value': sensor.value,
                    'units': sensor.units,
                    'health': sensor.health
                })
    
    # Если явные CPU-сенсоры не найдены, но есть общие "Temp" сенсоры
    if not cpu_temps and generic_temps:
        print("Используем общие 'Temp' сенсоры как CPU температуры")
        cpu_temps = generic_temps
    # Если никакие CPU сенсоры не найдены, используем все температурные сенсоры
    elif not cpu_temps:
        print("CPU температурные сенсоры не найдены. Используем все доступные температурные сенсоры:")
        for sensor in sensors:
            if sensor.type == 'Temperature' and sensor.value is not None:
                print(f"- {sensor.name}")
                cpu_temps.append({
                    'name': sensor.name,
                    'value': sensor.value,
                    'units': sensor.units,
                    'health': sensor.health
                })
    
    return cpu_temps

def calculate_fan_speed(cpu_temps):
    """Расчет оптимальной скорости вентиляторов на основе температур CPU"""
    if not cpu_temps:
        return 30  # Default speed if no CPU temp sensors found
    
    # Находим максимальную температуру CPU
    max_temp = max([sensor['value'] for sensor in cpu_temps])
    
    # Параметры сигмоидальной функции, настроенные под реальные серверные температуры
    min_speed = 0   # Минимальная скорость (%)
    max_speed = 100  # Максимальная скорость (%)
    mid_point = 75   # Точка перегиба (°C) - типичная рабочая температура сервера
    steepness = 0.15  # Крутизна кривой
    
    # Сигмоидальная функция для плавной кривой
    speed = min_speed + (max_speed - min_speed) / (1 + math.exp(-steepness * (max_temp - mid_point)))
    
    # Округляем до целого числа
    return int(round(speed))

def set_fan_speed(ipmi_conn, speed_percent):
    """Установка скорости вентиляторов в процентах (0-100)"""
    try:
        # Для Dell серверов используется команда raw для управления вентиляторами
        # Конвертируем для правильного формата команды
        data_bytes = [0x02, 0xff, speed_percent]
        
        # Выполнение команды через pyghmi
        result = ipmi_conn.raw_command(netfn=0x30, command=0x30, data=data_bytes)
        
        print(f"Установлена скорость вентиляторов: {speed_percent}%")
        return True
    except Exception as e:
        print(f"Ошибка при установке скорости вентиляторов: {str(e)}")
        return False

def clear_terminal():
    """Очистка терминала для разных ОС"""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_temperature(temp):
    """Форматирование температуры с цветом в зависимости от значения"""
    value = temp['value']
    if value >= 75:
        return f"{Fore.RED}{value}{temp['units']}{Style.RESET_ALL}"
    elif value >= 65:
        return f"{Fore.YELLOW}{value}{temp['units']}{Style.RESET_ALL}"
    else:
        return f"{Fore.GREEN}{value}{temp['units']}{Style.RESET_ALL}"

def format_fan_speed(fan):
    """Форматирование скорости вентилятора с цветом"""
    value = fan['value']
    if value <= 2000:
        return f"{Fore.GREEN}{value}{fan['units']}{Style.RESET_ALL}"
    elif value <= 4000:
        return f"{Fore.YELLOW}{value}{fan['units']}{Style.RESET_ALL}"
    else:
        return f"{Fore.RED}{value}{fan['units']}{Style.RESET_ALL}"

def display_dashboard(cpu_temps, fans, target_speed):
    """Отображение информационной панели с данными о температуре и вентиляторах"""
    clear_terminal()
    
    # Верхняя часть дисплея - заголовок и текущее время
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║ Dell R730 - Система контроля температуры                     ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║{Style.RESET_ALL} Время обновления: {now}                         {Fore.CYAN}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
    
    # Секция температур
    print(f"{Fore.CYAN}║ ТЕМПЕРАТУРЫ                                                 ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════╦═══════════════╦══════════════════╣{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║{Style.RESET_ALL} Датчик               {Fore.CYAN}║{Style.RESET_ALL} Значение      {Fore.CYAN}║{Style.RESET_ALL} Состояние        {Fore.CYAN}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════╬═══════════════╬══════════════════╣{Style.RESET_ALL}")
    
    for temp in cpu_temps:
        health_color = Fore.GREEN if temp['health'] == 'ok' else Fore.RED
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {temp['name']:<20} {Fore.CYAN}║{Style.RESET_ALL} {format_temperature(temp):<13} {Fore.CYAN}║{Style.RESET_ALL} {health_color}{temp['health']:<16}{Style.RESET_ALL} {Fore.CYAN}║{Style.RESET_ALL}")
    
    # Секция вентиляторов
    print(f"{Fore.CYAN}╠══════════════════════════╩═══════════════╩══════════════════╣{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║ ВЕНТИЛЯТОРЫ                                                 ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════╦═══════════════╦══════════════════╣{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║{Style.RESET_ALL} Вентилятор           {Fore.CYAN}║{Style.RESET_ALL} Скорость      {Fore.CYAN}║{Style.RESET_ALL} Состояние        {Fore.CYAN}║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════╬═══════════════╬══════════════════╣{Style.RESET_ALL}")
    
    for fan in fans:
        health_color = Fore.GREEN if fan['health'] == 'ok' else Fore.RED
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {fan['name']:<20} {Fore.CYAN}║{Style.RESET_ALL} {format_fan_speed(fan):<13} {Fore.CYAN}║{Style.RESET_ALL} {health_color}{fan['health']:<16}{Style.RESET_ALL} {Fore.CYAN}║{Style.RESET_ALL}")
    
    # Секция управления
    print(f"{Fore.CYAN}╠══════════════════════════╩═══════════════╩══════════════════╣{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║ УПРАВЛЕНИЕ                                                  ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
    
    # Отображение индикатора текущей скорости
    speed_bar_length = 40
    filled_length = int(speed_bar_length * target_speed / 100)
    bar = '█' * filled_length + '░' * (speed_bar_length - filled_length)
    
    speed_color = Fore.GREEN
    if target_speed > 60:
        speed_color = Fore.YELLOW
    if target_speed > 80:
        speed_color = Fore.RED
        
    print(f"{Fore.CYAN}║{Style.RESET_ALL} Заданная скорость: {speed_color}{target_speed}%{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║{Style.RESET_ALL} {speed_color}{bar}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}Для завершения программы нажмите Ctrl+C{Style.RESET_ALL}")

def main():
    # Параметры подключения
    hostname = "192.168.50.101"  # IP-адрес BMC/iDRAC
    username = "someuser"            # Пользователь IPMI
    password = "somepassword"        # Пароль IPMI
    kg_key = "somekey"  # K_g ключ без префикса 0x
    
    # Подключение к IPMI с использованием K_g ключа
    ipmi_conn = connect_to_ipmi(hostname, username, password, kg=kg_key)
    if not ipmi_conn:
        sys.exit(1)
    
    try:
        # Переключаемся на ручное управление вентиляторами
        ipmi_conn.raw_command(netfn=0x30, command=0x30, data=[0x01, 0x00])
        print(f"{Fore.GREEN}Включен ручной режим управления вентиляторами{Style.RESET_ALL}")
        time.sleep(1)
        
        while True:
            # Получение температур CPU
            cpu_temps = get_cpu_temperatures(ipmi_conn)
            if not cpu_temps:
                clear_terminal()
                print(f"{Fore.RED}Не удалось получить данные о температуре. Проверьте доступность сенсоров.{Style.RESET_ALL}")
                
                # Вывод всех доступных сенсоров для отладки
                print(f"\n{Fore.YELLOW}Список всех доступных сенсоров:{Style.RESET_ALL}")
                all_sensors = get_sensor_data(ipmi_conn)
                for sensor in all_sensors:
                    if sensor.value is not None:
                        print(f"- {sensor.name} ({sensor.type}): {sensor.value}{sensor.units}")
                
                # Ждем и пробуем снова вместо выхода
                time.sleep(30)
                continue
            
            # Расчет оптимальной скорости вентиляторов
            target_speed = calculate_fan_speed(cpu_temps)
            
            # Установка скорости вентиляторов
            set_fan_speed(ipmi_conn, target_speed)
            
            # Получение текущей информации о вентиляторах
            fans = get_fans(ipmi_conn)
            
            # Отображение информационной панели
            display_dashboard(cpu_temps, fans, target_speed)
            
            # Пауза перед следующим обновлением
            time.sleep(10)  # Обновление каждые 10 секунд
            
    except KeyboardInterrupt:
        # Возвращаем контроль вентиляторов обратно серверу при выходе
        clear_terminal()
        print(f"{Fore.YELLOW}Возвращаем автоматический режим управления вентиляторами...{Style.RESET_ALL}")
        ipmi_conn.raw_command(netfn=0x30, command=0x30, data=[0x00, 0x00])
        time.sleep(1)
        print(f"{Fore.GREEN}Возвращен автоматический режим управления вентиляторами{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Программа завершена{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Произошла ошибка: {str(e)}{Style.RESET_ALL}")
        # Пытаемся вернуть автоматическое управление
        try:
            ipmi_conn.raw_command(netfn=0x30, command=0x30, data=[0x00, 0x00])
            print(f"{Fore.GREEN}Возвращен автоматический режим управления вентиляторами{Style.RESET_ALL}")
        except:
            pass

if __name__ == "__main__":
    main()