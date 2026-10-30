import com.muyi.primevideo.MinimaxMatrixClient;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;

/** Reuse the unchanged Prime client signing helpers; credentials travel only on stdin/stdout pipes. */
public final class SignBridge {
    public static void main(String[] ignored) throws Exception {
        JSONObject in=new JSONObject(new String(System.in.readAllBytes(),StandardCharsets.UTF_8));
        JSONObject params=in.getJSONObject("params");StringBuilder query=new StringBuilder();
        for(String key:params.keySet()){
            if(query.length()>0)query.append('&');
            query.append(URLEncoder.encode(key,"UTF-8")).append('=').append(URLEncoder.encode(params.get(key).toString(),"UTF-8"));
        }
        String full=in.getString("url")+"?"+query;
        boolean post=in.optString("method").equals("POST");String body=in.optString("body");long ms=in.getLong("unix_ms");
        JSONObject out=new JSONObject().put("url",full).put("signature",MinimaxMatrixClient.signature((int)(ms/1000),post?body:""))
                .put("yy",MinimaxMatrixClient.yyHeader(full,post?body:"{}",ms)).put("timestamp",ms/1000);
        System.out.print(out);
    }
}
