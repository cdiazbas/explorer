"""Run the prototype's app/selftest.py with one of its looks, without changing the prototype (ROADMAP E0.8).

    <prototype python> bench/prototype_selftest.py <prototype dir> --look modern|classic <selftest arguments...>

app/look.py applies a look by wrapping startup.make_viewer, which selftest.py also calls to build its window; so
installing the look first and then running selftest.py as __main__ measures that look exactly as the viewer shows
it. Must run with the prototype's own Python environment (its versions), not explorer's.
"""
import os
import runpy
import sys


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--look":
        sys.exit(__doc__)
    proto, look_name, rest = os.path.abspath(sys.argv[1]), sys.argv[3], sys.argv[4:]
    app = os.path.join(proto, "app")
    sys.path.insert(0, app)
    import look  # the prototype's app/look.py

    applied = []
    apply = look.apply                                  # install() calls apply() by its global name: wrap it

    def apply_and_note(v, app_, name):
        r = apply(v, app_, name)
        applied.append(name)
        print(f"[bench] look '{name}' applied to the viewer", flush=True)
        return r

    look.apply = apply_and_note
    look.install(look_name)
    sys.argv = [os.path.join(app, "selftest.py")] + rest
    runpy.run_path(sys.argv[0], run_name="__main__")
    if applied != [look_name]:
        sys.exit(f"[bench] the look was not applied as asked: {applied}")
    out = rest[rest.index("--out") + 1] if "--out" in rest else None
    if out:                                             # the selftest's JSON records which look it measured
        import json

        d = json.load(open(out))
        d["look"] = look_name
        json.dump(d, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
