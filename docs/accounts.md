# Accounts: signing in, and who is a reviewer

Two separate questions, and they are answered in different places.

* **Can this person sign in?** Supabase Auth decides. One account per email
  address, per Supabase project.
* **May this person approve a rule change, or add another reviewer?** The
  `app_admins` table decides, and the API checks it on every write.

Nothing in the browser decides either one. The admin screen asks
`GET /api/admin/me` and lays itself out from the answer, so a browser that
claims to be a reviewer gets a reviewer-looking page and a 403 on each action.

## Making someone a reviewer

Open **#/admin → Reviewers**, type their email, and that is all. It writes a
row to `app_admins`.

**Their email can be added before they have ever signed up.** The grant is by
email address, and the check happens when a request arrives: the API reads the
email out of the verified token and looks it up. So the normal order for a new
client is

1. add `their.name@company.com` on the Reviewers tab,
2. they sign up with that address on the onboarding pages (`#/classic`),
3. they are a reviewer from their first request - nothing else to do.

Case and surrounding spaces do not matter; the table normalises the address and
a `CHECK` constraint keeps it that way.

Two refusals are deliberate and the screen explains both: nobody can revoke
themselves, and the last remaining reviewer cannot be removed. Without the
second one, an empty table would lock the queue with no way back in through the
product.

### The two sources, and why there are two

The Reviewers tab lists where each grant comes from.

| Source | Set in | Removable in the page |
|---|---|---|
| `table` | `app_admins`, from the page itself | yes |
| `environment` | `MAZI_ADMIN_EMAILS` on the API host | no |

The environment list is a backstop, for the case where the table is empty or
wrong and nobody can get in to fix it. It is deliberately not editable from a
screen that could be reached with a stolen session. Day to day, the table is
the one to use; `MAZI_ADMIN_EMAILS` can stay unset.

The first row in the table came from `schema/migrations/004_app_admins.sql`,
which is how the screen had somewhere to start.

## Test accounts

| Account | Profile | Reviewer | For |
|---|---|---|---|
| `caliber1385@gmail.com` | none | yes | the reviewer's view: approving, adding people |
| `caliber1385+maya@gmail.com` | Maya, from the data team's seed row | no | the ordinary signed-in view |

Both are `+`-aliases or the real address of the project owner, so confirmation
mail is deliverable. Ask Kevin for the passwords; they are not in the
repository.

The second one is the interesting one. The data team seeded one `user_profile`
row - Maya, 34, mediterranean, avoids peanut, likes chicken and onion - with
their own `username` and `password_hash` columns and no link to an account, so
until now no one could sign in *as* Maya. Linking it is one column:

```sql
UPDATE user_profile
   SET auth_user_id = (SELECT id FROM auth.users WHERE email = '<their email>')
 WHERE user_id = '<the profile's user_id>';
```

That is what `GET /api/profile/me` reads, and what puts a name, a diet and an
allergy list in the header and on the recommendation and cook screens. An
account with no profile row is not an error: signing up creates the account,
and the profile appears when the onboarding questions are answered. The screens
say which of the two it is rather than showing a blank.

To make a third test account, sign up on `#/classic` like a real user. A
confirmation email is required - the project has email confirmation on - so use
an address you can read.
