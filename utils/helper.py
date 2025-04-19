import disnake
import config

async def safe_followup(inter, content=None, **kwargs):
    try:
        await inter.followup.send(content, **kwargs)
    except disnake.Forbidden:
        try:
            await inter.send("❌ I can’t speak here. Please check my permissions!", ephemeral=True,delete_after=config.message_timeout)
        except:
            pass
    except disnake.NotFound:
        try:
            await inter.send("❌ This interaction seems broken... try again.", ephemeral=True,delete_after=config.message_timeout)
        except:
            pass
    except disnake.HTTPException as e:
        try:
            await inter.send(f"❌ Something went wrong: {e}", ephemeral=True,delete_after=config.message_timeout)
        except:
            pass