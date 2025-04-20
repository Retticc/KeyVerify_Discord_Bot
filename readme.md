<div align="center">
  <h1> KeyVerify</h1>
  <p><strong>A Secure Discord Bot for License Verification via Payhip</strong></p>

  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python Version"></a>
    <a href="https://discord.com"><img src="https://img.shields.io/badge/Discord-Bot%20Ready-7289DA?logo=discord" alt="Discord Bot Ready"></a>
  </p>
</div>

---
[Invite bot to your Server](https://discord.com/oauth2/authorize?client_id=1314098590951673927&integration_type=0&permissions=268446720&redirect_uri=https%3A%2F%2Fdiscord.com%2Foauth2%2Fauthorize%3Fclient_id%3D1314098590951673927&response_type=code&scope=guilds.join+bot)
##  What is KeyVerify?

**KeyVerify** is a lightweight and secure Discord bot for automating license verification of Payhip digital products. It helps creators manage customer access to Discord roles in a streamlined and encrypted way.

---

##  Features

- **License Verification** – Secure and user-friendly verification via in-server modal.
- **Auto Role Reassignment** – Automatically reapply roles if a verified user rejoins.
- **Product Management** – Add, list, or remove products with optional auto-generated roles.
- **License Reset** – Reset usage count of a license for reactivations.
- **Audit Logging** – Track all verification attempts and role assignments.
- **Spam Protection** – Rate-limiting built-in to avoid abuse.
- **Encrypted Storage** – License keys and product secrets are safely encrypted.

---

##  Slash Command Overview

| Command             | Description                                                             |
|---------------------|-------------------------------------------------------------------------|
| `/start_verification` | Deploys the verification interface to a channel.                       |
| `/add_product`        | Add a new product with a secret and optional role.                     |
| `/remove_product`     | Remove a product from the server list.                                 |
| `/list_products`      | View all products and their associated roles.                          |
| `/reset_key`          | Reset usage for a license key on Payhip.                               |
| `/set_lchannel`       | Define the channel for verification logs.                              |
| `/remove_user`        | *(Coming soon)* Revoke a user's access and licenses.                   |

---

##  Security Practices

-  License keys and secrets are **AES-encrypted** before storage.
-  All commands are **permission-locked** to server owners or admins.
-  **Cooldown** logic prevents excessive or abusive interactions.
-  Optional logging ensures traceability in any server.

---

##  Installation & Setup

1. **Clone the repo:**
   ```bash
   git clone https://github.com/Fayelicious/KeyVerify_Discord_Bot.git

Install dependencies:

    pip install -r requirements.txt

Create a .env file in the bot root:

    DATABASE_URL=your_postgres_connection_url
    PAYHIP_API_KEY=your_payhip_api_key

Run the bot:

    python bot.py

Make sure your bot has required permissions: Manage Roles, Send Messages, and Read Message History.

Project Status
KeyVerify is actively in development and used in live communities like Poodle's Discord. Feedback, contributions, and issue reports are always welcome!

Support & Contact
For help or to suggest a feature:

Discord: Fayelicious_    


Built With
    disnake

    Payhip API

    PostgreSQL + asyncpg

    Python 3.11+

Legal for Hosted Bot

  [Privacy Policy](https://payhip.com/Fayelicious/privacy-policy-discord-bot)
  [Terms of Service](https://payhip.com/Fayelicious/discordbot-tos?)

  Link to hosted Bot
    [KeyVerify](https://payhip.com/Fayelicious/payhip-license-verify-bot)
   
