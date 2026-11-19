# Verify first

Never invent an API. Check the installed version before you call it.

- MUST read the installed package before using any library API you have not already read in this session: open `node_modules/<pkg>/package.json` for the version, then the type declarations or source for the exact function signature.
- MUST check `package.json` for the real script names before running or documenting a command. NEVER assume `npm test`, `npm run lint` or similar exists.
- MUST confirm a file or directory exists before you edit, import or reference it.
- MUST NOT use a method because its name sounds right. If you cannot find it in the installed source, say so and ask.
- MUST state the installed version you checked when you report on library work (for example "react 19.3.1").
- When behaviour depends on the environment (ports, proxy, hostnames), probe it with a command and report the result. NEVER guess.
- If a check cannot be run, say exactly which check and why. NEVER report "done" for something you did not verify.
