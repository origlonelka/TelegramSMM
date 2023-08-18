using BattleBitAPI;
using BattleBitAPI.Common;
using BattleBitAPI.Server;
using System.Net;
using System.Text;
using System.Net.Http;
using System.Threading.Tasks;
using System.Numerics;
using CommunityServerAPI.Models;
using Microsoft.EntityFrameworkCore;
using CommunityServerAPI.Repositories;

class Program
{
    static void Main(string[] args)
    {
        var listener = new ServerListener<MyPlayer, MyGameServer>();

        using (var context = new DatabaseContext())
        {
            context.Database.Migrate();
        }

        listener.Start(29294);

        if (listener.IsListening)
            Console.Out.WriteLine($"Started API Server on port {listener.ListeningPort}");

        Thread.Sleep(-1);
    }
}
class MyPlayer : Player<MyPlayer>
{
    public bool IsOwner;
    public bool IsAdmin;
    public bool IsModer;
    public bool IsVip;
}
class MyGameServer : GameServer<MyPlayer>
{
    string reportwebhookUrl = "https://discord.com/api/webhooks/1140740838146719815/G7F-WqsywamMSUDZ3xtdEYe_QW64QiRN4Nf_kR_8CBXcvh0kRRYosE5fCPvpIM2AFE43";
    string chatwebhookUrl = "https://discord.com/api/webhooks/1140756394560200875/NjhJtzCKZXKG-hFmBwGezkdVHizw9DPXui67HBisob9sQnHrI7LwSWE-sxruiFgLoc_e";
    string commandwebhookUrl = "https://discord.com/api/webhooks/1140756985025933403/RMRqzkin2qC3Odm7drB9lW3d9oBTLzCVAuRabBO-BX3uT9DgrHPoCvwmeT8niFXWbMUm";
    public override async Task<bool> OnPlayerTypedMessage(MyPlayer player, ChatChannel channel, string msg)
    {
        string playerName = player.Name;
        string messageContent = msg.Replace("\"", "\\\"");
        string json = $"{{ \"content\": \"{playerName} ({player.SteamID}): {messageContent}\" }}";

        using (HttpClient client = new HttpClient())
        {
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await client.PostAsync(chatwebhookUrl, content);
        }

        if (msg.StartsWith("!"))
        {
            string cmdjson = $"{{ \"content\": \"{playerName}  ({player.SteamID}): {messageContent}\" }}";

            // Отправка POST-запроса с использованием HttpClient
            using (HttpClient client = new HttpClient())
            {
                var content = new StringContent(cmdjson, Encoding.UTF8, "application/json");
                var response = await client.PostAsync(commandwebhookUrl, content);
            }
        }
        if (msg.StartsWith("!"))
        {
            if (msg == "!help")
            {
                player.Message("!discord - Ссылка на наш дискорд \r\n !report [SteamID] [Причина] - Отправить репорт на игрока");
            }
            if (msg == "!discord")
            {
                player.Message("Наш дискорд: https://discord.gg/2k3p9PA3eC");
            }
            if (msg == "!report")
            {
                player.Message("Правильно писать так: !report [SteamID] [Причина]");
            }
            if (msg.StartsWith("!report"))
            {
                string[] arguments = msg.Split(' ');

                if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                {
                    string report = string.Join(" ", arguments, 2, arguments.Length - 2);
                    string jsonPayload = $@"{{ ""content"": ""<@&1139941661355561021> Игрок {player.Name} отправил репорт на игрока {steamid}: {report}"" }}";
                    using (HttpClient client = new HttpClient())
                    {
                        var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");
                        var response = await client.PostAsync(reportwebhookUrl, content);
                    }
                }
            }
            await using var bannedWeapons = new BannedWeaponRepository();
            if (player.IsOwner)
            {
                if (msg == "!help")
                {
                    player.Message("!discord - Ссылка на наш дискорд \r\n !report [SteamID] [Причина] - Отправить репорт на игрока \r\n !kick [SteamID] - Кикнуть игрока \r\n !setserverpass [Пароль] - Изменить пароль на сервере \r\n !setserverping [Максимально пинг] - Изменить максимальный пинг на сервере \r\n !an [Текст] - Объявление в UI \r\n !say [Текст] - Объявление в чат \r\n !forcestart - Запустить матч \r\n !endgame - Завершить матч \r\n !kill [SteamID] - Убить игрока \r\n !squadkick [SteamID] - Кикнуть игрока со сквада \r\n !squaddisband [SteamID] - Распустить сквад \r\n !squadpromote [SteamID] - Повысить до сквад лидера \r\n !warn [SteamdID] [Сообщение] - Выдать предупреждение игроку \r\n !setgamerole [steamdID] [Assault = 0, Medic = 1, Support = 2, Engineer = 3, Recon = 4, Leader = 5] - Сменить игровую роль игрока \r\n !sethp [SteamID] [HP] - Установить хп игроку \r\n !banweapon [оружие] - Заблокировать оружие \r\n !unbanweapon [оружие] - Разаблокировать оружие");
                }
                if (msg == "!banweapon")
                {
                    player.Message("Правильно писать так: !banweapon оружие");
                }
                if (msg.StartsWith("!banweapon"))
                {
                    string argument = msg.Substring("!banweapon ".Length); // Извлекаем аргумент после "kick "

                    if (!string.IsNullOrEmpty(argument))
                    {
                        await bannedWeapons.CreateAsync(new BannedWeapon { Name = argument });
                    }
                }
                if (msg == "!unbanweapon")
                {
                    player.Message("Правильно писать так: !unbanweapon оружие");
                }
                if (msg.StartsWith("!unbanweapon"))
                {
                    string argument = msg.Substring("!unbanweapon ".Length); // Извлекаем аргумент после "kick "

                    if (!string.IsNullOrEmpty(argument))
                    {
                        await bannedWeapons.DeleteAsync(new BannedWeapon { Name = argument });
                    }
                }
                if (msg == "!kick")
                {
                    player.Message("Правильно писать так: !kick steamid");
                }
                if (msg.StartsWith("!kick"))
                {
                    string argument = msg.Substring("!kick ".Length); // Извлекаем аргумент после "kick "

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamId))
                    {
                        Kick(steamId, "Вас кикнул Администратор"); // Передаем аргумент и причину
                    }
                }
                if (msg == "!setserverpass")
                {
                    player.Message("Правильно писать так: !setserverpass password");
                }
                if (msg.StartsWith("!setserverpass"))
                {
                    string argument = msg.Substring("!setserverpass ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        SetNewPassword(argument);
                    }
                }
                if (msg == "!setserverping")
                {
                    player.Message("Правильно писать так: !setserverping ping");
                }
                if (msg.StartsWith("!setserverping"))
                {
                    string argument = msg.Substring("!setserverping ".Length);

                    if (!string.IsNullOrEmpty(argument) && int.TryParse(argument, out int ping))
                    {
                        SetPingLimit(ping);
                    }
                }
                if (msg == "!an")
                {
                    player.Message("Правильно писать так: !an текст");
                }
                if (msg.StartsWith("!an"))
                {
                    string argument = msg.Substring("!an ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        AnnounceLong(argument);
                    }
                }
                if (msg == "!say")
                {
                    player.Message("Правильно писать так: !say текст");
                }
                if (msg.StartsWith("!say"))
                {
                    string argument = msg.Substring("!say ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        SayToChat(argument);
                    }
                }
                if (msg == "!forcestart")
                {
                    ForceStartGame();
                }
                if (msg == "!endgame")
                {
                    ForceEndGame();
                }
                if (msg == "!kill")
                {
                    player.Message("Правильно писать так: !kill steamdid");
                }
                if (msg.StartsWith("!kill"))
                {
                    string argument = msg.Substring("!kill ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        Kill(steamid);
                    }
                }
                if (msg == "!squadkick")
                {
                    player.Message("Правильно писать так: !squadkick steamdid");
                }
                if (msg.StartsWith("!squadkick"))
                {
                    string argument = msg.Substring("!squadkick ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        KickFromSquad(steamid);
                    }
                }
                if (msg == "!squaddisband")
                {
                    player.Message("Правильно писать так: !squaddisband steamdid");
                }
                if (msg.StartsWith("!squaddisband"))
                {
                    string argument = msg.Substring("!squaddisband ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        DisbandPlayerSquad(steamid);
                    }
                }
                if (msg == "!squadpromote")
                {
                    player.Message("Правильно писать так: !squadpromote steamdid");
                }
                if (msg.StartsWith("!squadpromote"))
                {
                    string argument = msg.Substring("!squadpromote ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        PromoteSquadLeader(steamid);
                    }
                }
                if (msg == "!warn")
                {
                    player.Message("Правильно писать так: !warn steamdid сообщение");
                }
                if (msg.StartsWith("!warn"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        string warningMessage = string.Join(" ", arguments, 2, arguments.Length - 2);
                        WarnPlayer(steamid, warningMessage);
                    }
                }
                if (msg == "!setgamerole")
                {
                    player.Message("Правильно писать так: !setgamerole steamdid role");
                }
                if (msg.StartsWith("!setgamerole"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        string gameroleString = string.Join(" ", arguments, 2, arguments.Length - 2);

                        if (Enum.TryParse(gameroleString, true, out GameRole gamerole))
                        {
                            SetRoleTo(steamid, gamerole);
                        }
                        else
                        {
                            player.Message("Неверная роль игрока.");
                        }
                    }
                }
                if (msg == "!sethp")
                {
                    player.Message("Правильно писать так: !sethp steamdid кол-во хп");
                }
                if (msg.StartsWith("!sethp"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        if (float.TryParse(arguments[2], out float hp))
                        {
                            SetHP(steamid, hp);
                        }
                    }
                }
            }

            if (player.IsAdmin)
            {
                if (msg == "!help")
                {
                    player.Message("!discord - Ссылка на наш дискорд \r\n !report [SteamID] [Причина] - Отправить репорт на игрока \r\n !kick [SteamID] - Кикнуть игрока \r\n !an [Текст] - Объявление в UI \r\n !say [Текст] - Объявление в чат \r\n !forcestart - Запустить матч \r\n !endgame - Завершить матч \r\n !kill [SteamID] - Убить игрока \r\n !squadkick [SteamID] - Кикнуть игрока со сквада \r\n !squaddisband [SteamID] - Распустить сквад \r\n !squadpromote [SteamID] - Повысить до сквад лидера \r\n !warn [SteamdID] [Сообщение] - Выдать предупреждение игроку \r\n !setgamerole [steamdID] [Assault = 0, Medic = 1, Support = 2, Engineer = 3, Recon = 4, Leader = 5] - Сменить игровую роль игрока \r\n !sethp [SteamID] [HP] - Установить хп игроку");
                }
                if (msg == "!kick")
                {
                    player.Message("Правильно писать так: !kick steamid");
                }
                if (msg.StartsWith("!kick"))
                {
                    string argument = msg.Substring("!kick ".Length); // Извлекаем аргумент после "kick "

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamId))
                    {
                        Kick(steamId, "Вас кикнул Администратор"); // Передаем аргумент и причину
                    }
                }
                if (msg == "!an")
                {
                    player.Message("Правильно писать так: !an текст");
                }
                if (msg.StartsWith("!an"))
                {
                    string argument = msg.Substring("!an ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        AnnounceLong(argument);
                    }
                }
                if (msg == "!say")
                {
                    player.Message("Правильно писать так: !say текст");
                }
                if (msg.StartsWith("!say"))
                {
                    string argument = msg.Substring("!say ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        SayToChat(argument);
                    }
                }
                if (msg == "!forcestart")
                {
                    ForceStartGame();
                }
                if (msg == "!endgame")
                {
                    ForceEndGame();
                }
                if (msg == "!kill")
                {
                    player.Message("Правильно писать так: !kill steamdid");
                }
                if (msg.StartsWith("!kill"))
                {
                    string argument = msg.Substring("!kill ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        Kill(steamid);
                    }
                }
                if (msg == "!squadkick")
                {
                    player.Message("Правильно писать так: !squadkick steamdid");
                }
                if (msg.StartsWith("!squadkick"))
                {
                    string argument = msg.Substring("!squadkick ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        KickFromSquad(steamid);
                    }
                }
                if (msg == "!squaddisband")
                {
                    player.Message("Правильно писать так: !squaddisband steamdid");
                }
                if (msg.StartsWith("!squaddisband"))
                {
                    string argument = msg.Substring("!squaddisband ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        DisbandPlayerSquad(steamid);
                    }
                }
                if (msg == "!squadpromote")
                {
                    player.Message("Правильно писать так: !squadpromote steamdid");
                }
                if (msg.StartsWith("!squadpromote"))
                {
                    string argument = msg.Substring("!squadpromote ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        PromoteSquadLeader(steamid);
                    }
                }
                if (msg == "!warn")
                {
                    player.Message("Правильно писать так: !warn steamdid сообщение");
                }
                if (msg.StartsWith("!warn"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        string warningMessage = string.Join(" ", arguments, 2, arguments.Length - 2);
                        WarnPlayer(steamid, warningMessage);
                    }
                }
                if (msg == "!setgamerole")
                {
                    player.Message("Правильно писать так: !setgamerole steamdid role");
                }
                if (msg.StartsWith("!setgamerole"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        string gameroleString = string.Join(" ", arguments, 2, arguments.Length - 2);

                        if (Enum.TryParse(gameroleString, true, out GameRole gamerole))
                        {
                            SetRoleTo(steamid, gamerole);
                        }
                        else
                        {
                            player.Message("Неверная роль игрока.");
                        }
                    }
                }
                if (msg == "!sethp")
                {
                    player.Message("Правильно писать так: !sethp steamdid кол-во хп");
                }
                if (msg.StartsWith("!sethp"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        if (float.TryParse(arguments[2], out float hp))
                        {
                            SetHP(steamid, hp);
                        }
                    }
                }
            }

            if (player.IsModer)
            {
                if (msg == "!help")
                {
                    player.Message("!discord - Ссылка на наш дискорд \r\n !report [SteamID] [Причина] - Отправить репорт на игрока \r\n !kick [SteamID] - Кикнуть игрока \r\n !an [Текст] - Объявление в UI \r\n !say [Текст] - Объявление в чат \r\n !kill [SteamID] - Убить игрока \r\n !squadkick [SteamID] - Кикнуть игрока со сквада \r\n !warn [SteamdID] [Сообщение] - Выдать предупреждение игроку");
                }
                if (msg == "!kick")
                {
                    player.Message("Правильно писать так: !kick steamid");
                }
                if (msg.StartsWith("!kick"))
                {
                    string argument = msg.Substring("!kick ".Length); // Извлекаем аргумент после "kick "

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamId))
                    {
                        Kick(steamId, "Вас кикнул Администратор"); // Передаем аргумент и причину
                    }
                }
                if (msg == "!an")
                {
                    player.Message("Правильно писать так: !an текст");
                }
                if (msg.StartsWith("!an"))
                {
                    string argument = msg.Substring("!an ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        AnnounceLong(argument);
                    }
                }
                if (msg == "!say")
                {
                    player.Message("Правильно писать так: !say текст");
                }
                if (msg.StartsWith("!say"))
                {
                    string argument = msg.Substring("!say ".Length);

                    if (!string.IsNullOrEmpty(argument))
                    {
                        SayToChat(argument);
                    }
                }
                if (msg == "!kill")
                {
                    player.Message("Правильно писать так: !kill steamdid");
                }
                if (msg.StartsWith("!kill"))
                {
                    string argument = msg.Substring("!kill ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        Kill(steamid);
                    }
                }
                if (msg == "!squadkick")
                {
                    player.Message("Правильно писать так: !squadkick steamdid");
                }
                if (msg.StartsWith("!squadkick"))
                {
                    string argument = msg.Substring("!squadkick ".Length);

                    if (!string.IsNullOrEmpty(argument) && ulong.TryParse(argument, out ulong steamid))
                    {
                        KickFromSquad(steamid);
                    }
                }
                if (msg == "!warn")
                {
                    player.Message("Правильно писать так: !warn steamdid сообщение");
                }
                if (msg.StartsWith("!warn"))
                {
                    string[] arguments = msg.Split(' ');

                    if (arguments.Length >= 3 && ulong.TryParse(arguments[1], out ulong steamid))
                    {
                        string warningMessage = string.Join(" ", arguments, 2, arguments.Length - 2);
                        WarnPlayer(steamid, warningMessage);
                    }
                }
            }

            if (player.IsVip)
            {
                if (msg == "!help")
                {
                    player.Message("!discord - Ссылка на наш дискорд \r\n !report [SteamID] [Причина] - Отправить репорт на игрока");
                }
            }
        }

        return true;
    }

    public override async Task OnPlayerConnected(MyPlayer player)
    {
        player.IsOwner = false;
        player.IsAdmin = false;
        player.IsModer = false;
        player.IsVip = false;

        string steamIDToCheck = player.SteamID.ToString();
        string ownerurl = "https://aleksandrkirichek.ru/battlebit/roles/owners.txt";
        string adminurl = "https://aleksandrkirichek.ru/battlebit/roles/admins.txt";
        string moderurl = "https://aleksandrkirichek.ru/battlebit/roles/moders.txt";
        string vipurl = "https://aleksandrkirichek.ru/battlebit/roles/vip.txt";

        try
        {
            WebClient webClient = new WebClient();
            string content = webClient.DownloadString(ownerurl);

            string[] steamIDs = content.Split('\n');

            foreach (string steamID in steamIDs)
            {
                if (steamID.Trim() == steamIDToCheck)
                {
                    player.IsOwner = true;
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Произошла ошибка при чтении списка SteamID: " + ex.Message);
        }

        try
        {
            WebClient webClient = new WebClient();
            string content = webClient.DownloadString(adminurl);

            string[] steamIDs = content.Split('\n');

            foreach (string steamID in steamIDs)
            {
                if (steamID.Trim() == steamIDToCheck)
                {
                    player.IsAdmin = true;
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Произошла ошибка при чтении списка SteamID: " + ex.Message);
        }

        try
        {
            WebClient webClient = new WebClient();
            string content = webClient.DownloadString(moderurl);

            string[] steamIDs = content.Split('\n');

            foreach (string steamID in steamIDs)
            {
                if (steamID.Trim() == steamIDToCheck)
                {
                    player.IsModer = true;
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Произошла ошибка при чтении списка SteamID: " + ex.Message);
        }

        try
        {
            WebClient webClient = new WebClient();
            string content = webClient.DownloadString(vipurl);

            string[] steamIDs = content.Split('\n');

            foreach (string steamID in steamIDs)
            {
                if (steamID.Trim() == steamIDToCheck)
                {
                    player.IsVip = true;
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Произошла ошибка при чтении списка SteamID: " + ex.Message);
        }

        if (player.IsOwner)
        {
            SayToChat($"<color=blue>[+] <color=red>На сервер зашёл Владелец: {player.Name}!");
        }

        if (player.IsAdmin)
        {
            SayToChat($"<color=blue>[+] <color=green>На сервер зашёл Администратор: {player.Name}!");
        }

        if (player.IsModer)
        {
            SayToChat($"<color=blue>[+] <color=deepskyblue>На сервер зашёл Модератор: {player.Name}!");
        }

        if (player.IsVip)
        {
            SayToChat($"<color=blue>[+] <color=gold>На сервер зашёл VIP: {player.Name}!");
        }

        Console.WriteLine($"{player.Name} ({player.SteamID}, {player.IP}, {player.PingMs}) зашёл на сервер!");
    }

    public override async Task OnConnected()
    {
        ForceStartGame();
    }

    public override async Task OnPlayerJoiningToServer(ulong steamID, PlayerJoiningArguments args)
    {
    }
}