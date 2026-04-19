# Explain Like I'm Five

← [Back to the technical version](../README.md)

---

## What is this?

There's a website called **Polymarket** where people bet real money on things that might happen in the future. Stuff like:

- "Will it rain in New York tomorrow?"
- "Who will win the next election?"
- "Will Bitcoin go above $100,000 this month?"

You buy a "yes" or "no" ticket for somewhere between 1 cent and 99 cents. If you're right, your ticket turns into $1. If you're wrong, it turns into $0. The price of the ticket is basically how likely people think it is to happen — a 30¢ "yes" ticket means people think there's a 30% chance.

## What were we trying to do?

We wanted to find out: **can a regular person, sitting at home with a laptop and $1,000, make money on Polymarket by being clever?**

Not by guessing who wins the election. By finding **mistakes** — moments when the prices don't quite add up, and you can sneak in and grab a little bit of free money before anyone notices.

Imagine a vending machine that sometimes gives out $1.05 in change for a $1 bill, by accident. If you find one, you could stand there feeding it dollars all day. We were looking for the vending-machine bug, but for prediction markets.

## What did we find?

**The bug is not there.** Or if it is, you can't reach it.

We tried **ten different ways** to find free money. Every single one of them failed. Here's why, in the simplest form:

1. **The mistakes do exist** — prices sometimes don't add up right.
2. **But they only last about 1 minute** before someone fixes them.
3. **That someone is a robot**, running on a very fast computer, very close to Polymarket's servers.
4. **We live in New Zealand**, which is basically as far from those servers as you can get on Earth. By the time our laptop even *sees* the mistake, the robots have already grabbed it.
5. **And even if we did catch one**, the amount of free money is so small (a few dollars), that the cost of the trade eats most of it.

It's a bit like trying to catch pennies that drop off a conveyor belt — except the conveyor belt is in another country, and there are people standing right next to it with vacuum cleaners.

## So was the whole thing pointless?

No! A few things came out of it that are actually useful:

### 1. We built tools that work

Even though we didn't make money, we built software that **watches Polymarket in real time** and spots the moments when prices don't add up. If the rules of the game ever change — like if Polymarket opens up a new type of market the robots haven't figured out yet — these tools are ready to go.

### 2. We wrote down the "gotchas"

Polymarket's system has lots of weird quirks — little bugs and surprises in how their website and data work. We spent days being tripped up by them. Now we've written them all down in one place, so the next person doesn't have to waste those days.

### 3. We learned some rules that apply to everything

These are useful for anyone trying to evaluate "too good to be true" ideas:

- **Whatever number you estimate — divide it by 5.** People (and AIs) are naturally too optimistic. Dividing by 5 usually gets you closer to reality.
- **Before you do something, write down why it's a bad idea.** Then read it. If it still seems good, maybe it is.
- **Just because something used to work doesn't mean it works now.** Always check with fresh data.
- **If something looks like free money, you're probably missing something.** Figure out what the risk you can't see is.

## What about using AI to help?

This whole project was done with an AI assistant (Claude) helping out. Good news and bad news.

**The good news:** It made everything way faster. Like, genuinely weeks faster.

**The bad news:** The AI is really good at *sounding* right, even when it's wrong. It would confidently say "this strategy will make $3,000 a month!" when actually it would make $300. Or it would make up old numbers from its memory that weren't true anymore.

So the rule we landed on: **the AI is an amazing research helper, but a terrible judge.** You have to be the skeptical one. If it sounds too good, it probably is.

## So what's the big-picture lesson?

Three things:

1. **A solo person on a laptop probably can't beat the robots on Polymarket.** At least not for the kinds of "mistake-finding" strategies we tried. Markets with lots of money in them get cleaned up by professionals very quickly.

2. **But publishing the failure is still valuable.** Most people only share their wins. This whole repo is what a careful, honest "no, this doesn't work" looks like — which is useful for anyone thinking about trying the same thing.

3. **AI-assisted research works, but you need guardrails.** The AI will make everything feel very productive. Some of that productivity is real, and some of it is a well-dressed illusion. Rules like "divide by 5" and "write the counter-memo" exist to catch the illusion before it costs you real money.

---

← [Back to the technical version](../README.md)
