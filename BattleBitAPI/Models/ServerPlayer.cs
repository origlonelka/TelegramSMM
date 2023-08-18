using System.ComponentModel.DataAnnotations.Schema;
using BattleBitAPI.Common;
using Microsoft.EntityFrameworkCore;

namespace CommunityServerAPI.Models;

[PrimaryKey(nameof(steamId))]

public class ServerPlayer
{
    // Remove auto increment etc.
    [DatabaseGenerated(DatabaseGeneratedOption.None)]
    public ulong steamId { get; set; }

    public PlayerStats stats { get; set; }
}