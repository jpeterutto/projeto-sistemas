package com.chat;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;
import com.chat.proto.ChatProtos.Message;
import com.chat.proto.ChatProtos.Message.Type;

import java.time.Instant;
import java.util.List;
import java.util.Arrays;

public class ClientBot {
    private static final String SENDER = System.getenv("BOT_NAME") != null ? System.getenv("BOT_NAME") : "bot_default";
    private static final String BROKER_URL = System.getenv("BROKER_URL") != null ? System.getenv("BROKER_URL") : "tcp://broker:5555";
    private static final String CHANNELS_ENV = System.getenv("CHANNELS_TO_CREATE") != null ? System.getenv("CHANNELS_TO_CREATE") : "#geral";

    public static void main(String[] args) {
        System.out.println("Iniciando client: " + SENDER);
        List<String> channelsToCreate = Arrays.asList(CHANNELS_ENV.split(","));
        
        try (ZContext context = new ZContext()) {
            ZMQ.Socket socket = context.createSocket(SocketType.REQ);
            socket.connect(BROKER_URL);
            
            try { Thread.sleep(3000); } catch (Exception e){}
            
            boolean loggedIn = false;
            while (!loggedIn) {
                Message loginReq = Message.newBuilder()
                    .setType(Type.LOGIN_REQ)
                    .setTimestamp(Instant.now().toString())
                    .setSender(SENDER)
                    .setLoginReq(Message.LoginRequest.newBuilder().setUsername(SENDER).build())
                    .build();
                
                logMessage("out", "broker", "LOGIN_REQ", "user=" + SENDER, "");
                socket.send(loginReq.toByteArray(), 0);
                
                byte[] reply = socket.recv(0);
                Message repMessage = Message.parseFrom(reply);
                
                boolean success = repMessage.getLoginRep().getSuccess();
                String resultStr = success ? "OK" : "ERROR";
                logMessage("in", repMessage.getSender(), "LOGIN_REP", "status=" + resultStr, resultStr);
                
                if (success) {
                    loggedIn = true;
                } else {
                    System.out.println("Erro de login: " + repMessage.getLoginRep().getErrorMessage() + ". Retentando em 5s...");
                    try { Thread.sleep(5000); } catch (Exception e){}
                }
            }
            
            Message listReq = Message.newBuilder()
                .setType(Type.LIST_CHANNELS_REQ)
                .setTimestamp(Instant.now().toString())
                .setSender(SENDER)
                .setListReq(Message.ListChannelsRequest.newBuilder().build())
                .build();
            
            logMessage("out", "broker", "LIST_CHANNELS_REQ", "", "");
            socket.send(listReq.toByteArray(), 0);
            
            byte[] listReply = socket.recv(0);
            Message listRepMessage = Message.parseFrom(listReply);
            List<String> existingChannels = listRepMessage.getListRep().getChannelsList();
            logMessage("in", listRepMessage.getSender(), "LIST_CHANNELS_REP", "channels=" + existingChannels, "OK");
            
            for (String ch : channelsToCreate) {
                ch = ch.trim();
                if (!existingChannels.contains(ch)) {
                    Message createReq = Message.newBuilder()
                        .setType(Type.CREATE_CHANNEL_REQ)
                        .setTimestamp(Instant.now().toString())
                        .setSender(SENDER)
                        .setCreateReq(Message.CreateChannelRequest.newBuilder().setChannelName(ch).build())
                        .build();
                    
                    logMessage("out", "broker", "CREATE_CHANNEL_REQ", "channel=" + ch, "");
                    socket.send(createReq.toByteArray(), 0);
                    
                    byte[] createReply = socket.recv(0);
                    Message createRepMessage = Message.parseFrom(createReply);
                    boolean success = createRepMessage.getCreateRep().getSuccess();
                    logMessage("in", createRepMessage.getSender(), "CREATE_CHANNEL_REP", "channel=" + ch, success ? "OK" : "ERROR");
                } else {
                    System.out.println("Canal " + ch + " ja existia na lista lida.");
                }
            }
            
            listReq = Message.newBuilder()
                .setType(Type.LIST_CHANNELS_REQ)
                .setTimestamp(Instant.now().toString())
                .setSender(SENDER)
                .setListReq(Message.ListChannelsRequest.newBuilder().build())
                .build();
            logMessage("out", "broker", "LIST_CHANNELS_REQ", "", "");
            socket.send(listReq.toByteArray(), 0);
            
            listReply = socket.recv(0);
            Message finalListRep = Message.parseFrom(listReply);
            logMessage("in", finalListRep.getSender(), "LIST_CHANNELS_REP", "channels=" + finalListRep.getListRep().getChannelsList(), "OK");
            
            System.out.println(SENDER + " finalizou o roteiro automatico de entregas parte 1 operando.");
            while (true) {
                try { Thread.sleep(100000); } catch (Exception e){}
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void logMessage(String direction, String target, String msgType, String content, String result) {
        String ts = Instant.now().toString();
        String resStr = result.isEmpty() ? "" : " | result=" + result;
        if (direction.equals("in")) {
            System.out.printf("[%s] SERVER %s -> CLIENT %s | %s | %s%s%n", ts, target, SENDER, msgType, content, resStr);
        } else {
            System.out.printf("[%s] CLIENT %s -> SERVER %s | %s | %s%s%n", ts, SENDER, target, msgType, content, resStr);
        }
    }
}
