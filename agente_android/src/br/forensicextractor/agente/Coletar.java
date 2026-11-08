package br.forensicextractor.agente;

import android.app.Activity;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Lê agenda, chamadas, SMS e MMS dos provedores do sistema e grava cada
 * fonte, como veio, num arquivo de linhas JSON na área privada do agente.
 *
 * Nada é interpretado aqui: cada linha do provedor vira um objeto com TODAS
 * as colunas, pelo nome e com o valor que o sistema devolveu. Interpretar é
 * trabalho da estação, que assim pode ser refeito sem voltar ao aparelho.
 *
 * O que não pôde ser lido é dito: `estado.json` traz, por fonte, quantos
 * registros vieram ou o erro que o sistema deu. Ele é gravado POR ÚLTIMO e
 * de uma vez (arquivo temporário renomeado), de modo que a presença dele
 * significa que a coleta terminou — nunca que parou no meio.
 */
public class Coletar extends Activity {

    static final String[][] FONTES = {
        {"contatos", "content://com.android.contacts/data/phones"},
        {"chamadas", "content://call_log/calls"},
        {"sms", "content://sms"},
        {"mms", "content://mms"},
        {"mms_partes", "content://mms/part"},
    };

    static final String VERSAO = "1";

    @Override
    protected void onCreate(Bundle estadoSalvo) {
        super.onCreate(estadoSalvo);
        final TextView texto = new TextView(this);
        texto.setPadding(48, 96, 48, 48);
        texto.setTextSize(18);
        texto.setText("Hexis Forensics\n\nAgente de coleta em execução.\n"
                + "Este aplicativo apenas lê agenda, chamadas e mensagens, e é "
                + "removido ao final da aquisição.");
        setContentView(texto);

        new Thread(new Runnable() {
            @Override
            public void run() {
                coletar();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        finish();
                    }
                });
            }
        }).start();
    }

    void coletar() {
        File pasta = getFilesDir();
        new File(pasta, "estado.json").delete();
        JSONArray fontes = new JSONArray();
        List<String> idsDeMms = new ArrayList<String>();

        for (String[] fonte : FONTES) {
            fontes.put(despejar(pasta, fonte[0], fonte[1], "mms".equals(fonte[0]) ? idsDeMms : null));
        }

        // Os enderecos de cada MMS moram num caminho proprio, um por mensagem.
        JSONObject enderecos = new JSONObject();
        int totalDeEnderecos = 0;
        String erroDeEnderecos = null;
        BufferedWriter saida = null;
        try {
            saida = abrir(new File(pasta, "mms_enderecos.jsonl"));
            for (String id : idsDeMms) {
                Cursor cursor = null;
                try {
                    cursor = getContentResolver().query(
                            Uri.parse("content://mms/" + id + "/addr"), null, null, null, null);
                    while (cursor != null && cursor.moveToNext()) {
                        JSONObject linha = linhaDe(cursor);
                        linha.put("_mms_id", id);
                        saida.write(linha.toString());
                        saida.newLine();
                        totalDeEnderecos++;
                    }
                } finally {
                    if (cursor != null) cursor.close();
                }
            }
        } catch (Throwable erro) {
            erroDeEnderecos = erro.getClass().getName() + ": " + erro.getMessage();
        } finally {
            fechar(saida);
        }
        try {
            enderecos.put("nome", "mms_enderecos");
            enderecos.put("uri", "content://mms/<id>/addr");
            enderecos.put("registros", totalDeEnderecos);
            enderecos.put("erro", erroDeEnderecos == null ? JSONObject.NULL : erroDeEnderecos);
            fontes.put(enderecos);

            JSONObject estado = new JSONObject();
            estado.put("agente", getPackageName());
            estado.put("versao_do_agente", VERSAO);
            estado.put("api_do_aparelho", android.os.Build.VERSION.SDK_INT);
            estado.put("concluido_em_epoch_ms", System.currentTimeMillis());
            estado.put("fontes", fontes);

            File temporario = new File(pasta, "estado.json.tmp");
            BufferedWriter escritor = abrir(temporario);
            escritor.write(estado.toString(2));
            fechar(escritor);
            temporario.renameTo(new File(pasta, "estado.json"));
        } catch (Throwable erro) {
            // Sem estado.json a estacao sabe que a coleta nao terminou.
        }
    }

    /** Grava uma fonte inteira e devolve o que aconteceu com ela. */
    JSONObject despejar(File pasta, String nome, String uri, List<String> ids) {
        JSONObject resumo = new JSONObject();
        int registros = 0;
        String erro = null;
        boolean respondeu = false;
        Cursor cursor = null;
        BufferedWriter saida = null;
        try {
            saida = abrir(new File(pasta, nome + ".jsonl"));
            cursor = getContentResolver().query(Uri.parse(uri), null, null, null, null);
            respondeu = cursor != null;
            while (cursor != null && cursor.moveToNext()) {
                JSONObject linha = linhaDe(cursor);
                saida.write(linha.toString());
                saida.newLine();
                registros++;
                if (ids != null && linha.has("_id")) {
                    ids.add(String.valueOf(linha.get("_id")));
                }
            }
        } catch (Throwable falha) {
            erro = falha.getClass().getName() + ": " + falha.getMessage();
        } finally {
            if (cursor != null) cursor.close();
            fechar(saida);
        }
        try {
            resumo.put("nome", nome);
            resumo.put("uri", uri);
            resumo.put("registros", registros);
            // O provedor devolver `null` nao e o mesmo que devolver zero
            // linhas: e uma recusa sem excecao.
            resumo.put("provedor_respondeu", respondeu);
            resumo.put("erro", erro == null ? JSONObject.NULL : erro);
        } catch (Throwable ignorado) {
            // JSONObject.put so falha com chave nula.
        }
        return resumo;
    }

    /** Uma linha do provedor, com todas as colunas e o tipo que o sistema devolveu. */
    static JSONObject linhaDe(Cursor cursor) throws Exception {
        JSONObject linha = new JSONObject();
        for (int coluna = 0; coluna < cursor.getColumnCount(); coluna++) {
            String nome = cursor.getColumnName(coluna);
            switch (cursor.getType(coluna)) {
                case Cursor.FIELD_TYPE_NULL:
                    linha.put(nome, JSONObject.NULL);
                    break;
                case Cursor.FIELD_TYPE_INTEGER:
                    linha.put(nome, cursor.getLong(coluna));
                    break;
                case Cursor.FIELD_TYPE_FLOAT:
                    linha.put(nome, cursor.getDouble(coluna));
                    break;
                case Cursor.FIELD_TYPE_BLOB:
                    JSONObject binario = new JSONObject();
                    binario.put("_base64", Base64.encodeToString(cursor.getBlob(coluna), Base64.NO_WRAP));
                    linha.put(nome, binario);
                    break;
                default:
                    linha.put(nome, cursor.getString(coluna));
            }
        }
        return linha;
    }

    static BufferedWriter abrir(File arquivo) throws Exception {
        return new BufferedWriter(
                new OutputStreamWriter(new FileOutputStream(arquivo, false), StandardCharsets.UTF_8));
    }

    static void fechar(BufferedWriter escritor) {
        try {
            if (escritor != null) escritor.close();
        } catch (Throwable ignorado) {
            // nada a fazer: o estado.json dira se a fonte veio
        }
    }
}
