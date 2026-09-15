import org.tn5250j.framework.common.SessionManager;
import org.tn5250j.Session5250;
import org.tn5250j.framework.tn5250.Screen5250;
import org.tn5250j.framework.tn5250.ScreenField;
import org.tn5250j.framework.tn5250.ScreenFields;
import org.tn5250j.keyboard.KeyMnemonic;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Properties;

/**
 * CapturaHeadless — captura de pantallas 5250 sin ventana usando el stack de
 * tn5250j (negocia, loguea y recorre pantallas igual que el emulador real).
 *
 * Uso:
 *   java -cp .:<tn5250j.jar> CapturaHeadless <host> <puerto> [cmdsCsv] [salida.txt]
 *
 *   <host>/<puerto>  : host 5250 (o proxy TLS local; ver README.md).
 *   <cmdsCsv>        : opcional, comas separadas. Por defecto:
 *                      STRPDM, WRKLIBPDM, WRKOBJ *ALL, WRKMBRPDM FILE(QGPL/QRPGLESRC)
 *   <salida.txt>     : opcional; si se indica, el dump va a ese archivo
 *                      (además de stdout).
 *
 * Credenciales por entorno: ORACLE_USER / ORACLE_PASS (default C3S41/matica96).
 * La clase construye la sesión con el mismo Session5250 que usa la GUI de
 * tn5250j, por lo que supera la restricción CPF1296 de pub400 que bloquea al
 * cliente TN5250 plano de probe/colectores.
 */
public class CapturaHeadless {
    static Session5250 sess;
    static Screen5250 screen;
    static PrintStream out = System.out;

    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "127.0.0.1";
        String port = args.length > 1 ? args[1] : "9992";
        String cmdsCsv = args.length > 2 ? args[2] : "STRPDM,WRKLIBPDM,WRKOBJ *ALL,WRKMBRPDM FILE(QGPL/QRPGLESRC)";
        String salida = args.length > 3 ? args[3] : null;
        if (salida != null) {
            out = new PrintStream(Files.newOutputStream(Paths.get(salida)), true, "UTF-8");
        }
        Properties cp = new Properties();
        cp.setProperty("SESSION_HOST", host);
        cp.setProperty("SESSION_HOST_PORT", port);
        cp.setProperty("SESSION_SCREEN_SIZE", "80x24");
        cp.setProperty("SESSION_CODE_PAGE", "37");
        cp.setProperty("SESSION_TN_ENHANCED", "1");
        cp.setProperty("SESSION_KEEP_ALIVE_ENABLED", "false");
        cp.setProperty("SESSION_DEVICE_NAME", "C3");

        sess = SessionManager.instance().openSession(cp, "headless.session", "pubhead");
        sess.connect();
        Thread.sleep(4000);
        screen = sess.getScreen();

        esperarPantalla();
        out.println("=============== SIGNON ===============");
        dump("signon");

        out.println(">>> login: " + cfgUser());
        login(cfgUser(), cfgPass());
        esperarPantalla(6000);
        out.println("=============== POST-LOGIN ===============");
        String t0 = pantalla();
        dump("postlogin");
        if (!t0.contains("Seleccione una de las opciones") && !t0.contains("Select one of the following") && pantalla().trim().length() > 0) {
            // puede haber Display Messages
            if (pantalla().contains("Message") || pantalla().contains("Mensajes")) {
                out.println(">>> mensajes pendientes, ENTER");
                screen.sendKeys(KeyMnemonic.ENTER);
                esperarPantalla(3000);
                dump("main");
            }
        }

        String[] cmds = cmdsCsv.split(",", -1);
        for (String raw : cmds) {
            String cmd = raw.trim();
            if (cmd.isEmpty()) continue;
            out.println(">>> comando: " + cmd);
            enviarComando(cmd);
            esperarPantalla(4000);
            dump(cmd.replaceAll("\\s+", "_").replaceAll("\\(", "").replaceAll("\\)", "").replaceAll("/", "_"));
        }
        out.println("DONE");
        if (out != System.out) { out.flush(); out.close(); }
        sess.disconnect();
        System.exit(0);
    }

    static String cfgUser() { return System.getenv().getOrDefault("ORACLE_USER", "C3S41"); }
    static String cfgPass() { return System.getenv().getOrDefault("ORACLE_PASS", "matica96"); }

    static void login(String user, String pass) throws Exception {
        ScreenFields f = screen.getScreenFields();
        int n = f.getFieldCount();
        out.println("  fields signon: " + n);
        for (int i = 0; i < n; i++) {
            ScreenField sf = f.getField(i);
            out.println("    field " + i + ": start(" + sf.startRow() + "," + sf.startCol() + ") len=" + sf.getLength());
        }
        if (n >= 1) { screen.gotoField(1); Thread.sleep(150); screen.sendKeys(user); }
        if (n >= 2) { screen.gotoField(2); Thread.sleep(150); screen.sendKeys(pass); }
        Thread.sleep(200);
        screen.sendKeys(KeyMnemonic.ENTER);
    }

    static void enviarComando(String cmd) throws Exception {
        ScreenFields f = screen.getScreenFields();
        int n = f.getFieldCount();
        // localiza la línea "===>" por contenido
        int fila = -1;
        char[] chars = screen.getScreenAsChars();
        int cols = screen.getColumns();
        for (int i = 0; i < screen.getRows(); i++) {
            StringBuilder sb = new StringBuilder();
            for (int j = 0; j < cols && (i*cols+j) < chars.length; j++) sb.append(chars[i*cols+j]);
            int idx = sb.indexOf("===>");
            if (idx >= 0) { fila = i; break; }
        }
        if (fila >= 0) {
            // buscar el campo editable en esa fila, col extendida tras "===>"
            for (int i = 1; i <= n; i++) {
                ScreenField sf = f.getField(i-1);
                if (sf.startRow() == fila && sf.startCol() >= 5) { targetGoto(f, i); typeComando(cmd); return; }
            }
            // campo más cercano en la fila ===>
            int best = 1; int bestd = 9999;
            for (int i = 1; i <= n; i++) {
                ScreenField sf = f.getField(i-1);
                int d = Math.abs(sf.startRow() - fila);
                if (d < bestd) { bestd = d; best = i; }
            }
            targetGoto(f, best); typeComando(cmd); return;
        }
        // fallback: último campo con longitud > 30 (línea de mandato típica)
        for (int i = n; i >= 1; i--) {
            ScreenField sf = f.getField(i-1);
            if (sf.getLength() > 30 && sf.getLength() < 80) { targetGoto(f, i); typeComando(cmd); return; }
        }
        if (n >= 1) { targetGoto(f, n); typeComando(cmd); }
    }

    static void targetGoto(ScreenFields f, int i) throws Exception {
        screen.gotoField(i);
        Thread.sleep(120);
    }
    static void typeComando(String cmd) throws Exception {
        screen.sendKeys(cmd);
        Thread.sleep(200);
        screen.sendKeys(KeyMnemonic.ENTER);
    }

    static void esperarPantalla() throws Exception { esperarPantalla(3000); }
    static void esperarPantalla(long ms) throws Exception {
        long t0 = System.currentTimeMillis();
        int last = -1;
        while (System.currentTimeMillis() - t0 < ms) {
            char[] chars = screen.getScreenAsChars();
            if (chars != null) {
                int cnt = 0;
                for (char c : chars) if (c != ' ' && c != 0) cnt++;
                if (cnt != last) { last = cnt; t0 = System.currentTimeMillis(); }
            }
            Thread.sleep(250);
        }
    }

    static String pantalla() {
        char[] chars = screen.getScreenAsChars();
        if (chars == null) return "";
        int c = screen.getColumns(); int r = screen.getRows();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < r; i++) {
            for (int j = 0; j < c; j++) sb.append(chars[i*c+j]);
            sb.append('\n');
        }
        return sb.toString();
    }

    static char[] colorBuf = null;
    static Object planes;

    static void dump(String label) {
        char[] chars = screen.getScreenAsChars();
        if (chars == null) { out.println("[" + label + " screen nula]"); return; }
        int c = screen.getColumns(); int r = screen.getRows();
        // leer colores una vez
        if (colorBuf == null) {
            try {
                if (planes == null) {
                    java.lang.reflect.Field fp = Screen5250.class.getDeclaredField("planes");
                    fp.setAccessible(true); planes = fp.get(screen);
                }
                java.lang.reflect.Field fc = planes.getClass().getDeclaredField("screenColor");
                fc.setAccessible(true); colorBuf = (char[]) fc.get(planes);
            } catch (Exception e) { }
        }
        char[] colors = colorBuf;
        String txt = pantalla();
        out.println("### " + label + "  (" + r + "x" + c + ")");
        for (int i = 0; i < r; i++) {
            StringBuilder line = new StringBuilder();
            StringBuilder cols = new StringBuilder();
            boolean any = false;
            for (int j = 0; j < c; j++) {
                char ch = chars[i*c+j];
                line.append(ch != 0 ? ch : ' ');
                if (colors != null) cols.append(String.format("%x", (int) colors[i*c+j]));
                if (ch != ' ' && ch != 0) any = true;
            }
            if (any) {
                out.println("   |" + line.toString().replaceAll("\\s+$", "") + "|");
                out.println("    colors: " + cols.toString().replaceAll("\\s+$", ""));
            }
        }
        // campos
        try {
            ScreenFields f = screen.getScreenFields();
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < f.getFieldCount(); i++) {
                ScreenField sf = f.getField(i);
                sb.append("F" + i + "(" + sf.startRow() + "," + sf.startCol() + ",len" + sf.getLength() + ") ");
            }
            out.println("   fields: " + sb.toString());
        } catch (Exception e) { }
        out.println();
    }
}