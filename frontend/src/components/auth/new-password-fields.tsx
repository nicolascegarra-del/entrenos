import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const MIN_PASSWORD = 10;

export const passwordReady = (password: string, repeat: string) =>
  password.length >= MIN_PASSWORD && password === repeat;

/** Contraseña nueva + repetir, con avisos de longitud y coincidencia. */
export function NewPasswordFields({
  password,
  repeat,
  onPassword,
  onRepeat,
  label = "Contraseña",
}: {
  password: string;
  repeat: string;
  onPassword: (v: string) => void;
  onRepeat: (v: string) => void;
  label?: string;
}) {
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = repeat.length > 0 && repeat !== password;
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="new-password">{label}</Label>
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          aria-invalid={tooShort}
          onChange={(e) => onPassword(e.target.value)}
          className="h-11 md:h-9"
        />
        <p
          className={
            tooShort
              ? "text-sm text-destructive"
              : "text-xs text-muted-foreground"
          }
        >
          Mínimo {MIN_PASSWORD} caracteres.
        </p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="repeat-password">Repite la contraseña</Label>
        <Input
          id="repeat-password"
          type="password"
          autoComplete="new-password"
          value={repeat}
          aria-invalid={mismatch}
          onChange={(e) => onRepeat(e.target.value)}
          className="h-11 md:h-9"
        />
        {mismatch && <p className="text-sm text-destructive">No coincide.</p>}
      </div>
    </>
  );
}
